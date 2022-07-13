import six
import dateutil
import copy
import hashlib
import json
import time
import requests
import re

from mastodon import Mastodon, MastodonAPIError, MastodonBadGatewayError, MastodonGatewayTimeoutError, MastodonIllegalArgumentError, MastodonInternalServerError, MastodonNotFoundError, MastodonRatelimitError, MastodonServerError, MastodonServiceUnavailableError, MastodonUnauthorizedError, StreamListener
from mastodon.Mastodon import MastodonMalformedEventError, MastodonNetworkError, MastodonReadTimeout
from requests.exceptions import ChunkedEncodingError, ReadTimeout

# Mastodon.py はいくつか不具合があり、bookmarks()やdomain_blocks()がエラーになったりする
# のえるさんが bookmarks() を修正したものがあった https://blog.noellabo.jp/entry/2021/03/07/153405 
# ので、domain_blocks() もなんちゃって修正
# VoTLMasGでは現時点で使わないが一応残しておく
'''
toots = []
result = mastodon.domain_blocks(limit = 40)
toots += result
while hasattr(result[-1], '_pagination_next'):
  result = mastodon.domain_blocks(limit = 40, max_id = result[-1]._pagination_next['max_id'])
  toots += result
for i in toots:
  print(i.value)
'''    

# StreamListnerをスレッドで使うとなんかエラーが出るのでエラーを無視するようにしたものを定義

class StreamListenerEx(StreamListener):
    def handle_stream(self, response):
        """
        Handles a stream of events from the Mastodon server. When each event
        is received, the corresponding .on_[name]() method is called.

        response; a requests response object with the open stream for reading.
        """
        event = {}
        line_buffer = bytearray()
        try:
            for chunk in response.iter_content(chunk_size = 1):
                if chunk:
                    for chunk_part in chunk:
                        chunk_part = bytearray([chunk_part])
                        if chunk_part == b'\n':
                            try:
                                line = line_buffer.decode('utf-8')
                            except UnicodeDecodeError as err:
                                exception = MastodonMalformedEventError("Malformed UTF-8")
                                self.on_abort(exception)
                                six.raise_from(
                                    exception,
                                    err
                                )
                            if line == '':
                                self._dispatch(event)
                                event = {}
                            else:
                                event = self._parse_line(line, event)
                            line_buffer = bytearray()
                        else:
                            line_buffer.extend(chunk_part)
        except ChunkedEncodingError as err:
            exception = MastodonNetworkError("Server ceased communication.")
            self.on_abort(exception)
            six.raise_from(
                exception,
                err
            )
        except MastodonReadTimeout as err:
            exception = MastodonReadTimeout("Timed out while reading from server."),
            self.on_abort(exception)
            six.raise_from(
                exception,
                err
            )

    def _parse_line(self, line, event):
        if line.startswith(':'):
            self.handle_heartbeat()
        else:
            try:
                key, value = line.split(': ', 1)
            except:
                exception = MastodonMalformedEventError("Malformed event.")
                self.on_abort(exception)
                raise exception
            # According to the MDN spec, repeating the 'data' key
            # represents a newline(!)
            if key in event:
                event[key] += '\n' + value
            else:
                event[key] = value
        return event
    
    def _dispatch(self, event):
        try:
            name = event['event']
            data = event['data']
            payload = json.loads(data, object_hook = Mastodon._Mastodon__json_hooks)
        except KeyError as err:
            exception = MastodonMalformedEventError('Missing field', err.args[0], event)
            self.on_abort(exception)
            six.raise_from(
                exception,
                err
            )
        except ValueError as err:
            # py2: plain ValueError
            # py3: json.JSONDecodeError, a subclass of ValueError
            exception = MastodonMalformedEventError('Bad JSON', data)
            self.on_abort(exception)
            six.raise_from(
                exception,
                err
            )

        # ERROR ('Bad event type', 'emoji_reaction', 'status.update')
        handler_name = 'on_' + name
        try:
            handler = getattr(self, handler_name)
        except AttributeError as err:
            errs = ['emoji_reaction', 'status.update']
            f = False
            for i in errs:
                if i == name:
                    f = True
                    break
            if f == False:
                print('Bad event type : ' + name)
        else:
            handler(payload)


class MastodonEx(Mastodon):
    def bookmarks(self, max_id=None, min_id=None, since_id=None, limit=None):
        if max_id != None:
            max_id = super()._Mastodon__unpack_id(max_id)
    
        if min_id != None:
            min_id = super()._Mastodon__unpack_id(min_id)        
    
        if since_id != None:
            since_id = super()._Mastodon__unpack_id(since_id)
    
        params = super()._Mastodon__generate_params(locals())
        return super()._Mastodon__api_request('GET', '/api/v1/bookmarks', params)

    def domain_blocks(self, max_id=None, min_id=None, since_id=None, limit=None):
        """
        Fetch the logged-in user's blocked domains.

        Returns a list of blocked domain URLs (as strings, without protocol specifier).
        """
        # max_id = self.__unpack_id(max_id) を
        # min_id = super()._Mastodon__unpack_id(min_id) にする
        
        if max_id != None:
            max_id = super()._Mastodon__unpack_id(max_id)
        
        if min_id != None:
            min_id = super()._Mastodon__unpack_id(min_id)        
        
        if since_id != None:
            since_id = super()._Mastodon__unpack_id(since_id)
            
        params = super()._Mastodon__generate_params(locals())
        return self.__api_request('GET', '/api/v1/domain_blocks', params)
      
    def __api_request(self, method, endpoint, params={}, files={}, headers={}, access_token_override=None, base_url_override=None, do_ratelimiting=True, use_json=False, parse=True):
        """
        Internal API request helper.
        """
        response = None
        remaining_wait = 0
        
        # "pace" mode ratelimiting: Assume constant rate of requests, sleep a little less long than it
        # would take to not hit the rate limit at that request rate.
        if do_ratelimiting and self.ratelimit_method == "pace":
            if self.ratelimit_remaining == 0:
                to_next = self.ratelimit_reset - time.time()
                if to_next > 0:
                    # As a precaution, never sleep longer than 5 minutes
                    to_next = min(to_next, 5 * 60)
                    time.sleep(to_next)
            else:
                time_waited = time.time() - self.ratelimit_lastcall
                time_wait = float(self.ratelimit_reset - time.time()) / float(self.ratelimit_remaining)
                remaining_wait = time_wait - time_waited

            if remaining_wait > 0:
                to_next = remaining_wait / self.ratelimit_pacefactor
                to_next = min(to_next, 5 * 60)
                time.sleep(to_next)

        # Generate request headers
        headers = copy.deepcopy(headers)
        if not self.access_token is None:
            headers['Authorization'] = 'Bearer ' + self.access_token
        if not access_token_override is None:
            headers['Authorization'] = 'Bearer ' + access_token_override

        # Determine base URL
        base_url = self.api_base_url
        if not base_url_override is None:
            base_url = base_url_override

        if self.debug_requests:
            print('Mastodon: Request to endpoint "' + base_url + endpoint + '" using method "' + method + '".')
            print('Parameters: ' + str(params))
            print('Headers: ' + str(headers))
            print('Files: ' + str(files))

        # Make request
        request_complete = False
        while not request_complete:
            request_complete = True

            response_object = None
            try:
                kwargs = dict(headers=headers, files=files,
                              timeout=self.request_timeout)
                if use_json == False:
                    if method == 'GET':
                        kwargs['params'] = params
                    else:
                        kwargs['data'] = params
                else:
                    kwargs['json'] = params
                
                # Block list with exactly three entries, matching on hashes of the instance API domain
                # For more information, have a look at the docs
                if hashlib.sha256(",".join(base_url.split("//")[-1].split("/")[0].split(".")[-2:]).encode("utf-8")).hexdigest() in \
                    [
                        "f3b50af8594eaa91dc440357a92691ff65dbfc9555226e9545b8e083dc10d2e1", 
                        "b96d2de9784efb5af0af56965b8616afe5469c06e7188ad0ccaee5c7cb8a56b6",
                        "2dc0cbc89fad4873f665b78cc2f8b6b80fae4af9ac43c0d693edfda27275f517"
                    ]:
                    raise Exception("Access denied.")
                    
                response_object = self.session.request(method, base_url + endpoint, **kwargs)
            except Exception as e:
                raise MastodonNetworkError("Could not complete request: %s" % e)

            if response_object is None:
                raise MastodonIllegalArgumentError("Illegal request.")

            # Parse rate limiting headers
            if 'X-RateLimit-Remaining' in response_object.headers and do_ratelimiting:
                self.ratelimit_remaining = int(response_object.headers['X-RateLimit-Remaining'])
                self.ratelimit_limit = int(response_object.headers['X-RateLimit-Limit'])

                try:
                    ratelimit_reset_datetime = dateutil.parser.parse(response_object.headers['X-RateLimit-Reset'])
                    self.ratelimit_reset = super()._Mastodon__datetime_to_epoch(ratelimit_reset_datetime) ### ERROR

                    # Adjust server time to local clock
                    if 'Date' in response_object.headers:
                        server_time_datetime = dateutil.parser.parse(response_object.headers['Date'])
                        server_time = super()._Mastodon__datetime_to_epoch(server_time_datetime) ### ERROR
                        server_time_diff = time.time() - server_time
                        self.ratelimit_reset += server_time_diff
                        self.ratelimit_lastcall = time.time()
                except Exception as e:
                    raise MastodonRatelimitError("Rate limit time calculations failed: %s" % e)

            # Handle response
            if self.debug_requests:
                print('Mastodon: Response received with code ' + str(response_object.status_code) + '.')
                print('response headers: ' + str(response_object.headers))
                print('Response text content: ' + str(response_object.text))

            if not response_object.ok:
                try:
                    response = response_object.json(object_hook=self.__json_hooks)
                    if isinstance(response, dict) and 'error' in response:
                        error_msg = response['error']
                    elif isinstance(response, str):
                        error_msg = response
                    else:
                        error_msg = None
                except ValueError:
                    error_msg = None

                # Handle rate limiting
                if response_object.status_code == 429:
                    if self.ratelimit_method == 'throw' or not do_ratelimiting:
                        raise MastodonRatelimitError('Hit rate limit.')
                    elif self.ratelimit_method in ('wait', 'pace'):
                        to_next = self.ratelimit_reset - time.time()
                        if to_next > 0:
                            # As a precaution, never sleep longer than 5 minutes
                            to_next = min(to_next, 5 * 60)
                            time.sleep(to_next)
                            request_complete = False
                            continue

                if response_object.status_code == 404:
                    ex_type = MastodonNotFoundError
                    if not error_msg:
                        error_msg = 'Endpoint not found.'
                        # this is for compatibility with older versions
                        # which raised MastodonAPIError('Endpoint not found.')
                        # on any 404
                elif response_object.status_code == 401:
                    ex_type = MastodonUnauthorizedError
                elif response_object.status_code == 500:
                    ex_type = MastodonInternalServerError
                elif response_object.status_code == 502:
                    ex_type = MastodonBadGatewayError
                elif response_object.status_code == 503:
                    ex_type = MastodonServiceUnavailableError
                elif response_object.status_code == 504:
                    ex_type = MastodonGatewayTimeoutError
                elif response_object.status_code >= 500 and \
                     response_object.status_code <= 511:
                    ex_type = MastodonServerError
                else:
                    ex_type = MastodonAPIError

                raise ex_type(
                        'Mastodon API returned error',
                        response_object.status_code,
                        response_object.reason,
                        error_msg)

            if parse == True:
                try:
                    response = response_object.json(object_hook=super()._Mastodon__json_hooks) ### ERROR
                except:
                    raise MastodonAPIError( ### ERROR
                        "Could not parse response as JSON, response code was %s, "
                        "bad json content was '%s'" % (response_object.status_code,
                                                    response_object.content))
            else:
                response = response_object.content
                
            # Parse link headers
            if isinstance(response, list) and \
                    'Link' in response_object.headers and \
                    response_object.headers['Link'] != "":
                tmp_urls = requests.utils.parse_header_links(
                    response_object.headers['Link'].rstrip('>').replace('>,<', ',<'))
                for url in tmp_urls:
                    if 'rel' not in url:
                        continue

                    if url['rel'] == 'next':
                        # Be paranoid and extract max_id specifically
                        next_url = url['url']
                        matchgroups = re.search(r"[?&]max_id=([^&]+)", next_url)

                        if matchgroups:
                            next_params = copy.deepcopy(params)
                            next_params['_pagination_method'] = method
                            next_params['_pagination_endpoint'] = endpoint
                            max_id = matchgroups.group(1)
                            if max_id.isdigit():
                                next_params['max_id'] = int(max_id)
                            else:
                                next_params['max_id'] = max_id
                            if "since_id" in next_params:
                                del next_params['since_id']
                            if "min_id" in next_params:
                                del next_params['min_id']
                            
                            class result_data:
                              pass
                            
                            if type(response[-1]) != type('abc'):
                                response[-1]._pagination_next = next_params # ERROR
                            else:
                              ls = []
                              for t in response:
                                tmp = result_data()                              
                                tmp.value = t
                                ls.append(tmp)

                              response = ls                                
                              response[-1]._pagination_next = next_params

                    if url['rel'] == 'prev':
                        # Be paranoid and extract since_id or min_id specifically
                        prev_url = url['url']
                        
                        # Old and busted (pre-2.6.0): since_id pagination
                        matchgroups = re.search(r"[?&]since_id=([^&]+)", prev_url)
                        if matchgroups:
                            prev_params = copy.deepcopy(params)
                            prev_params['_pagination_method'] = method
                            prev_params['_pagination_endpoint'] = endpoint
                            since_id = matchgroups.group(1)
                            if since_id.isdigit():
                                prev_params['since_id'] = int(since_id)
                            else:
                                prev_params['since_id'] = since_id
                            if "max_id" in prev_params:
                                del prev_params['max_id']

                            class result_data:
                              pass
                            
                            if type(response[-1]) != type('abc'):
                                response[-1]._pagination_prev = prev_params # ERROR
                            else:
                              ls = []
                              for t in response:
                                tmp = result_data()                              
                                tmp.value = t
                                ls.append(tmp)

                              response = ls                                
                              response[-1]._pagination_prev = prev_params
                            
                        # New and fantastico (post-2.6.0): min_id pagination
                        matchgroups = re.search(r"[?&]min_id=([^&]+)", prev_url)
                        if matchgroups:
                            prev_params = copy.deepcopy(params)
                            prev_params['_pagination_method'] = method
                            prev_params['_pagination_endpoint'] = endpoint
                            min_id = matchgroups.group(1)
                            if min_id.isdigit():
                                prev_params['min_id'] = int(min_id)
                            else:
                                prev_params['min_id'] = min_id
                            if "max_id" in prev_params:
                                del prev_params['max_id']

                            class result_data:
                              pass
                            
                            if type(response[-1]) != type('abc'):
                                response[-1]._pagination_prev = prev_params # ERROR
                            else:
                              ls = []
                              for t in response:
                                tmp = result_data()                              
                                tmp.value = t
                                ls.append(tmp)

                              response = ls                                
                              response[-1]._pagination_prev = prev_params

        return response

