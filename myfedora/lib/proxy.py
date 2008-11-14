from fedora.client import ProxyClient
from Cookie import SimpleCookie
from urlparse import urljoin
import urllib2
from pylons import request
import inspect

class MFProxyClient(ProxyClient):
    def __init__(self, base_url, useragent=None, debug=False, return_auth=False):
        super(MFProxyClient, self).__init__(base_url, 
                                            useragent=useragent, 
                                            debug=debug,
                                            session_as_cookie=False)
        self._return_auth = return_auth
        
    def convert_to_simple_cookie(self, cookie):
        sc = SimpleCookie()
        for key, value in cookie.iteritems():
            sc[key] = value
            
        return sc

    def get_current_proxy_cookies(self):
        cookies = request.cookies
        return cookies
    
    def send_authenticated_request(self, method, req_params=None):
        sessionid = request.cookies.get('tg-visit')
        
        auth_params = {'session_id': sessionid}
        result = self.send_request(method,
                                   req_params = req_params,
                                   auth_params = auth_params)
            
        return result

    def send_request(self, method, req_params=None, auth_params=None):
        result = super(MFProxyClient, self).send_request(method, 
                                                         req_params=req_params, 
                                                         auth_params=auth_params)
        
        if not self._return_auth:
            result = result[1]
            
        return result
    
    # TODO: make proxyclient able to handle non-json requests
    def get_page(self, path, req_params = None):
        method = path.lstrip('/')
        url = urljoin(self.base_url, method)

        response = None # the data that we get back from the server

        req = urllib2.Request(url)
        req.add_header('User-agent', self.useragent)

        # If the cookie exists, send it so that visit tracking works.
        c = self.convert_to_simple_cookie(self.get_current_proxy_cookies())
        req.add_header('Cookie', c.output(attrs=[], header='').strip())

        try:
            response = urllib2.urlopen(req)
        except urllib2.HTTPError, e:
            if e.msg == 'Forbidden':
                if (inspect.currentframe().f_back.f_code !=
                        inspect.currentframe().f_code):
                    self._authenticate(force=True)
                    return self.send_request(method, auth, req_params)
                else:
                    # We actually shouldn't ever reach here.  Unless something
                    # goes drastically wrong _authenticate should raise an
                    # AuthError
                    log.error(e)
                    raise AuthError, _('Unable to log into server: %(error)s') \
                            % {'error': str(e)}
            else:
                raise

        data = response.read()
        
        return data
         
class FasClient(MFProxyClient):
    def __init__(self, baseURL='https://admin.fedoraproject.org/accounts'):
        super(FasClient, self).__init__(baseURL)
    
    def user_list(self, search):
        result = self.send_authenticated_request('user/list/',
                                                 req_params = {'search': search})
        
        return result
    
    def group_list(self, search, groups_only=False):
        result = self.send_authenticated_request('group/list/',
                                                 req_params = {'search': search})
        if groups_only:
            result = {'groups': result['groups']} 
        
        return result
    
    def get_user_info(self, user, full_results=False):
        result = self.send_authenticated_request('user/view/' + user)
        
        return result
    
class PkgdbClient(MFProxyClient):
    def __init__(self, baseURL='https://admin.fedoraproject.org/pkgdb'):
        super(PkgdbClient, self).__init__(baseURL)
        
    def get_package_info(self, name):
        result = self.send_authenticated_request("packages/name", 
                                               req_params={'packageName': name})
        
        return result
    
    def get_user_packages(self, user, acls=None, limit=10, page=1):
        result = self.send_authenticated_request("users/packages/" + user,
                                                 req_params={'acls':acls,
                                                             'pkgs_tgp_limit': limit,
                                                             'pkgs_tgp_no': page})
        
        return result
    
    def get_collections(self, create_table=False, hide_obsolete=False):
        results = self.send_authenticated_request("collections/")
        
        if hide_obsolete or create_table:
            ctable={}
            collections = []
            for c in results['collections']:
              if hide_obsolete and c['statuscode'] == 9:
                  continue
              
              collections.append(c)
              if create_table:
                  ctable[c['id']] = c
                  
            if ctable:
                results['collections_table'] = ctable
            results['collections'] = collections
              
        return results
    
class BodhiClient(MFProxyClient):
    def __init__(self, baseURL='https://admin.fedoraproject.org/updates'):
        super(BodhiClient, self).__init__(baseURL)
        
    def get_info(self, package='', get_auth=False):
         result = self.send_authenticated_request("list/",
                                                  req_params={'package': package,
                                                              'get_auth': get_auth}
                                                  )
         return result

    def query(self, release=None, status=None, type_=None, bugs=None,
              request=None, mine=None, package=None, username=None, limit=10,
              page=1, get_auth=True):
        """ Query bodhi for a list of updates.

        :kwarg release: The release that you wish to query updates for.
        :kwarg status: The update status (``pending``, ``testing``, ``stable``,
            ``obsolete``)
        :kwarg type_: The type of this update: ``security``, ``bugfix``,
            ``enhancement``, and ``newpackage``.
        :kwarg bugs: A list of Red Hat Bugzilla ID's
        :kwarg request: An update request to query for
            ``testing``, ``stable``, ``unpush``, ``obsolete`` or None.
        :kwarg mine: If True, only query the users updates.  Default: False.
        :kwarg package: A package name or a name-version-release.
        :kwarg limit: The maximum number of updates to display.  Default: 10.
        :kwarg username: username to look at

        """
        params = {
                'tg_paginate_limit': limit,
                'tg_paginate_no': page,
                'username': username,
                'get_auth': get_auth,
                'release': release,
                'package': package,
                'request': request,
                'status': status,
                'type_': type_,
                'bugs': bugs,
                'mine': mine,
                }

        # bodhi can't handle false query sting
        if not mine:
            del params['mine']

        for key, value in params.items():
            if value is None:
                del params[key]

        if params.get('mine'):
            return self.send_authenticated_request('list', req_params=params)

        return self.send_request('list', req_params=params)

    def save(self, builds='', type_='', bugs='', notes='', request='testing',
             close_bugs=True, suggest_reboot=False, inheritance=False,
             autokarma=True, stable_karma=3, unstable_karma=-3, edited=''):
        """ Save an update.

        This entails either creating a new update, or editing an existing one.
        To edit an existing update, you must specify the update title in
        the ``edited`` keyword argument.

        :kwarg builds: A list of koji builds for this update.
        :kwarg type\_: The type of this update: ``security``, ``bugfix``,
            ``enhancement``, and ``newpackage``.
        :kwarg bugs: A list of Red Hat Bugzilla ID's associated with this
            update.
        :kwarg notes: Details as to why this update exists.
        :kwarg request: Request for this update to change state, either to
            ``testing``, ``stable``, ``unpush``, ``obsolete`` or None.
        :kwarg close_bugs: Close bugs when update is stable
        :kwarg suggest_reboot: Suggest that the user reboot after update.
        :kwarg inheritance: Follow koji build inheritance, which may result in
            this update being pushed out to additional releases.
        :kwarg autokarma: Allow bodhi to automatically change the state of this
            update based on the ``karma`` from user feedback.  It will
            push your update to ``stable`` once it reaches the ``stable_karma``
            and unpush your update when reaching ``unstable_karma``.
        :kwarg stable_karma: The upper threshold for marking an update as
            ``stable``.
        :kwarg unstable_karma: The lower threshold for unpushing an update.
        :kwarg edited: The update title of the existing update that we are
            editing.

        """
        return self.send_authenticated_request('save', req_params={
                'suggest_reboot': suggest_reboot,
                'close_bugs': close_bugs,
                'unstable_karma': unstable_karma,
                'stable_karma': stable_karma,
                'inheritance': inheritance,
                'autokarma': autokarma,
                'request': request,
                'builds': builds,
                'edited': edited,
                'notes': notes,
                'type_': type_,
                'bugs': bugs,
                })

    def request(self, update, request):
        """ Request an update state change.

        :arg update: The title of the update
        :arg request: The request (``testing``, ``stable``, ``obsolete``)

        """
        return self.send_authenticated_request('request', req_params={
                'update': update,
                'action': request,
                })
