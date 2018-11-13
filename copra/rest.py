# -*- coding: utf-8 -*-
"""Public (unauthenticated) and authenticated asyncronous REST client 
for the Coinbase Pro platform.

"""

import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import sys
import time
import urllib.parse

import aiohttp
import dateutil.parser
from multidict import CIMultiDict

from copra import __version__

URL = 'https://api.pro.coinbase.com'
SANDBOX_URL = 'https://api-public.sandbox.pro.coinbase.com'

USER_AGENT = 'Python/{} copra/{}'.format(
                '.'.join([str(x) for x in sys.version_info[:3]]), __version__)
                
HEADERS = {'USER-AGENT': USER_AGENT}


class BaseClient():
    """Generic asyncronous REST client.
    
    This client provides the core GET/POST/DELETE functionality for the 
    copra.rest.Client class.
    """
    
    def __init__(self, loop):
        """
        
        :param loop: The asyncio loop that the client runs in.
        :type loop: asyncio loop
        """
        self.loop = loop
        self.session = aiohttp.ClientSession(loop=loop)
    
       
    @property
    def closed(self):
        """True if the client has been closed, False otherwise
        """
        return self.session.closed
        
        
    async def close(self):
        """Close the client session and release all aquired resources.
        """
        await self.session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.session.close()
        
    
    async def handle_error(self, response):
        """Handle HTTP client and server request errors.
        
        This method is called when the HTTP status code of the server's
        response is >= 400. Override this method to log errors, raise an
        exception, etc. The default is to do nothing.
        
        :param aiohttp.ClientResponse response: the response returned by the
            aiohttp request call.
        """
        pass
 
  
    async def _request(self, method, *args, **kwargs):
        """Base method for all requests. 
        
        The actual aiohttp call is made in this method, and status code 
        inspection is done here as well. All arguments except for method are
        passed "as is" to aiohttp.
        
        :param str method: The HTTP method of the request.
        
        :raises ValueError: If method is not delete, get, or post
        """
        if method not in ('delete', 'get', 'post'):
            raise ValueError(
               'Inavlid method {}. Must be delete, get, or post'.format(method))
               
        resp = await getattr(self.session, method)(*args, **kwargs)
        
        if resp.status >= 400:
            await self.handle_error(resp)
            
        return resp
        

    async def delete(self, url, params=None, headers=HEADERS):
        """Method for making DELETE requests.
        
        :param str url The url of the resource to be DELETEd.

        :param dict params: (optional) key/value pairs to be sent as parameters 
            in the query string of the request.
            
        :param dict headers: (optional) key/value pairs to be sent as headers
            for the request. The default is just the USER-AGENT string for the
            copra client.
            
        :returns: aiohttp.ClientResponse object
        """
        if params:
            url += '?{}'.format(urllib.parse.urlencode(params))
            
        return await self._request('delete', url, headers=headers)
        
        
    async def get(self, url, params=None, headers=HEADERS):
        """Method for making GET requests.
        
        :param str url: The url of the resource to be retrieved.
        
        :param dict params: (optional) key/value pairs to be sent as parameters 
            in the query string of the request.
            
        :param dict headers: (optional) key/value pairs to be sent as headers
            for the request. The default is just the USER-AGENT string for the
            copra client. This can also be any MultiDict variant.
            
        :returns: aiohttp.ClientResponse object 
        """
        if params:
            url += '?{}'.format(urllib.parse.urlencode(params))
            
        return await self._request('get', url, headers=headers)

        
    async def post(self, url, data={}, headers=HEADERS):
        """Method for making POST requests.
        
        :param str url The url of the resource to be POST'ed to.
            
        :param dict data: (optional) Key/value str pairs to be sent in the 
            body of the request. The default is {}.
            
        :param dict headers: (optional) key/value pairs to be sent as headers
            for the request. The default is just the USER-AGENT string for the
            copra client.
            
        :returns: aiohttp.ClientResponse object
        """
        data = json.dumps(data) if data else ''
        return await self._request('post', url, data=data, headers=headers)
        
        
class APIRequestError(Exception):
    """Error returned by the server to an API endpoint request.
    
    These errors are generated by the Coinbase Pro API server. They cover isses
    such as invalid API key, forbidden access to resources, internal server
    errors, etc. The string representation of the error will display the message
    the server provided. The response field is the aiohttp.ClientResponse 
    object returned by the aiohttp request. It can be inspected to get more 
    detail including the HTTP status code, response headers, etc.
    
    :ivar aiohttp.ClientResponse: The ClientResponse object returned by the
        aiohttp request that caused the error.
    """
    def __init__(self, message, response):
        super().__init__(message)
        self.response = response
    
    
class Client(BaseClient):
    """Asyncronous REST client for Coinbase Pro.
    """
    
    def __init__(self, loop, url=URL, auth=False, key='', secret='', passphrase=''):
        """
        
        :param loop: The asyncio loop that the client runs in.
        :type loop: asyncio loop
        
        :param bool auth:  (optional) Whether or not the (entire) REST session is
            authenticated. If True, you will need an API key from the Coinbase 
            Pro website. The default is False.
            
        :param str key:  (optional) The API key to use for authentication. 
            Required if auth is True. The default is ''.
            
        :param str secret: (optional) The secret string for the API key used for
            authenticaiton. Required if auth is True. The default is ''.
            
        :param str passphrase: (optional) The passphrase for the API key used 
            for authentication. Required if auth is True. The default is ''.
            
        :raises ValueError: If auth is True and key, secret, and passphrase are
            not provided.
        """
        self.url = url
        
        if auth and not (key and secret and passphrase):
            raise ValueError('auth requires key, secret, and passphrase')
        
        self.auth = auth
        self.key = key
        self.secret = secret
        self.passphrase = passphrase

        super().__init__(loop)


    def get_auth_headers(self, path, method='GET', body={}, timestamp=None):
        """Get the headers necessary to authenticate a client request.
        
        :param str path: The path portion of the REST request. For example,
            '/products/BTC-USD/candles'
            
        :param str method: (optional) The method of the request. The default is
            GET.
            
        :param dict body: (optional) Dictionary of key/value str pairs
            to be sent in the body of the request. The default is {}.
            
        :param float timestamp: (optional) A UNIX timestamp. This parameter 
            exists for testing purposes and generally should not be used. If a 
            timestamp is provided it must be within 30 seconds of the API 
            server's time. This can be found using: 
            :meth:`rest.Client.server_time`.
            
        :returns: A dict of headers to be added to the request.
        
        :raises ValueError: If auth is not True.
        """
        if not self.auth:
            raise ValueError('client is not properly configured for authorization')
            
        body = json.dumps(body) if body else ''
        
        if not timestamp:
            timestamp = time.time()
        timestamp = str(timestamp)
        message = timestamp + method + path + body
        message = message.encode('ascii')
        hmac_key = base64.b64decode(self.secret)
        signature = hmac.new(hmac_key, message, hashlib.sha256)
        signature_b64 = base64.b64encode(signature.digest()).decode('utf-8')
        
        return {
            'USER-AGENT': USER_AGENT,
            'Content-Type': 'Application/JSON',
            'CB-ACCESS-SIGN': signature_b64,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-KEY': self.key,
            'CB-ACCESS-PASSPHRASE': self.passphrase
        }

     
    async def handle_error(self, response):
        """Handle http request errors.
        
        This method is called whenever an API call returns an HTTP status code
        of 400 or higher.
        
        :param aiohttp.ClientResponse response: the response returned by the
            aiohttp request call.
        """
        body = await response.json()
        msg = body['message'] + ' [{}]'.format(response.status)
        raise APIRequestError(msg, response)
 
 
    async def delete(self, path='/', params=None, auth=False):
        """Method for making DELETE requests.
        
        :param str path: (optional) The path not including the base URL of the
            resource to be deleted. The default is '/'.
            
        :param dict params: (optional) Dictionary of key/value str pairs
            to be appended to the request. The default is None.
            
        :param boolean auth: (optional) Indicates whether or not this request 
            needs to be authenticated. The default is False.
            
        :returns: A 2-tuple: (response header, response body). Headers is a dict 
            with the HTTP headers of the respone. The response body is a 
            JSON-formatted, UTF-8 encoded dict.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        req_headers = self.get_auth_headers(path, 'DELETE') if auth else HEADERS
        resp = await super().delete(self.url + path, params, headers=req_headers)
        body = await resp.json()
        headers = dict(resp.headers)
        return (headers, body)
        

    async def get(self, path='/', params=None, auth=False):
        """Method for making GET requests.
        
        :param str path: (optional) The path not including the base URL of the
            resource to be retrieved. The default is '/'.
            
        :param dict params: (optional) Dictionary of key/value str pairs
            to be appended to the request. The default is None.
            
        :param boolean auth: (optional) Indicates whether or not this request 
            needs to be authenticated. The default is False.
            
        :returns: A 2-tuple: (response header, response body). Headers is a dict 
            with the HTTP headers of the respone. The response body is a 
            JSON-formatted, UTF-8 encoded dict.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        req_headers = self.get_auth_headers(path) if auth else HEADERS
        resp = await super().get(self.url + path, params, headers=req_headers)
        body = await resp.json()
        headers = dict(resp.headers)
        return (headers, body)


    async def post(self, path='/', data=None, auth=False):
        """Base method for making POST requests.
        
        :param str path: (optional) The path not including the base URL of the
            resource to be POST'ed to. The default is '/'
            
        :param dict data: (optional) Dictionary of key/value str pairs
            to be sent in the body of the request. The default is None.
            
        :param boolean auth: (optional) Indicates whether or not this request 
            needs to be authenticated. The default is False.
            
        :returns: A 2-tuple: (response header, response body). Headers is a dict 
            with the HTTP headers of the respone. The response body is a 
            JSON-formatted, UTF-8 encoded dict.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        req_headers = self.get_auth_headers(path, 'POST', data) if auth else HEADERS
            
        resp = await super().post(self.url + path, data, headers=req_headers)
        body = await resp.json()
        headers = dict(resp.headers)
        return (headers, body)
            
            
    async def products(self):
        """Get a list of available currency pairs for trading.
        
        Returns a list of dicts where each dict represents a currency pair. 
        
        The base_min_size and base_max_size fields define the min and max order 
        size. The quote_increment field specifies the min order price as well 
        as the price increment. The order price must be a multiple of this 
        increment (i.e. if the increment is 0.01, order prices of 0.001 or 
        0.021 would be rejected).
        
        :returns: A list of dicts representing the currency pairs available
            for trading.
            
        :Example:
        
        [
          {
            'id': 'BTC-USD', 
            'base_currency': 'BTC', 
            'quote_currency': 'USD', 
            'base_min_size': '0.001', 
            'base_max_size': '70', 
            'quote_increment': '0.01', 
            'display_name': 'BTC/USD', 
            'status': 'online', 
            'margin_enabled': False, 
            'status_message': None, 
            'min_market_funds': '10', 
            'max_market_funds': '1000000', 
            'post_only': False, 
            'limit_only': False, 
            'cancel_only': False
          },
          ...
         ]
            
        .. note:: Product ID will not change once assigned to a product but 
            the min/max/quote sizes can be updated in the future.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/products')
        return body

        
    async def order_book(self, product_id, level=1):
        """Get a list of open orders for a product. 
        
        By default, only the inside (i.e. best) bid and ask are returned. This 
        is equivalent to a book depth of 1 level. If you would like to see a 
        larger order book, specify the level query parameter.

        :param str product_id: The product id whose order book you wish to 
            view. The product id is a string consisting of a base currency
            and a quote currency. eg., BTC-USD, ETH-EUR, etc. To see all of 
            the product ids, use :meth:`rest.Client.products`.
            
        :param int level: (optional) The level customizes the amount of detail 
            shown. See below for more detail. The default is 1.
            
         **Levels**
        
        +--------------------------------------------------------------------+
        | Level | Description                                                |
        +=======+============================================================+
        |   1   | Only the best bid and ask                                  |
        +-------+------------------------------------------------------------+
        |   2   | Top 50 bids and asks (aggregated)                          |
        +-------+------------------------------------------------------------+
        |   3   | Full order book (non aggregated)                           |
        +-------+------------------------------------------------------------+
        
        If a level is not aggregated, then all of the orders at each price 
        will be returned. Aggregated levels return only one size for each 
        active price (as if there was only a single order for that size at 
        the level).
        
        Levels 1 and 2 are aggregated. The first field is the price. The second
        is the size which is the sum of the size of the orders at that price, 
        and the third is the number of orders, the count of orders at 
        that price. The size should not be multiplied by the number of orders.

        Level 3 is non-aggregated and returns the entire order book.
        
        .. note:: This request is NOT paginated. The entire book is returned in 
            one response.
            
        .. note:: Level 1 and Level 2 are recommended for polling. For the most 
            up-to-date data, consider using the websocket stream.
            
        .. warning:: Level 3 is only recommended for users wishing to maintain 
            a full real-time order book using the websocket stream. Abuse of 
            Level 3 via polling will cause your access to be limited or 
            blocked.
            
        :returns: A dict representing the order book for the product id
            specified. The layout of the dict will vary based on the level. See
            the examples below.
            
        :Example:
        
        **Level 1**
        
        {
          'sequence': 7068939079, 
          'bids': [['6482.98', '54.49144003', 18]], 
          'asks': [['6482.99', '4.57036219', 10]]
        }
        
        **Level 2**
        
        {
          'sequence': 7069016926, 
          'bids': [['6489.13', '0.001', 1], ['6487.99', '0.03', 1], ...],
          'asks': [['6489.14', '40.72125158', 16], ['6490.11', '0.5', 1], ...],
        }
        
        **Level 3**
        
        {
          'sequence': 7072737439, 
          'bids': [
                    ['6468.9', '0.01100413', '48c3ed25-616d-430d-bab4-cb338b489a33'], 
                    ['6468.9', '0.224', 'b96424ea-e992-4df5-b503-df50dac1ac50'], 
                    ...
                  ],
          'asks': [
                    ['6468.91', '5.96606527', 'cc37e457-020c-4843-9a3e-e6164dcf4e60'], 
                    ['6468.91', '0.00341509', '43e8158a-30c6-437b-9a51-9b9da00e4e22'],
                    ...
                  ]
        }
           
        :raises ValueError: If level not 1, 2, or 3.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        
        if level not in (1, 2, 3):
            raise ValueError("level must be 1, 2, or 3")    
            
        headers, body = await self.get('/products/{}/book'.format(product_id), 
                                       params={'level': level})
        return body
 
        
    async def ticker(self, product_id):
        """Get information about the last trade for a specific product.
        
        :param str product_id: The product id of the tick to be retrieved.
            The product id is a string consisting of a base currency and a 
            quote currency. eg., BTC-USD, ETH-EUR, etc. To see all of the 
            product ids, use :meth:`rest.Client.products`.
            
        :returns: A dict containing information about the last trade (tick) for
           the product.
           
        :Example:
        
        {
          'trade_id': 51554088, 
          'price': '6503.14000000', 
          'size': '0.00532605', 
          'bid': '6503.13', 
          'ask': '6503.14', 
          'volume': '6060.89272148', 
          'time': '2018-09-27T13:18:42.571000Z'
        }
        
        .. note:: Polling is discouraged in favor of connecting via the 
            websocket stream and listening for match messages.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        header, body = await self.get('/products/{}/ticker'.format(product_id))
        return body

        
    async def trades(self, product_id, limit=100, before=None, after=None):
        """List the latest trades for a product.
        
        The trade side indicates the maker order side. The maker order is the 
        order that was open on the order book. buy side indicates a down-tick 
        because the maker was a buy order and their order was removed. 
        Conversely, sell side indicates an up-tick.
        
        .. note:: This method is paginated. Methods that can return multiple 
            pages of results return a 3-tuple instead of a dict or list like most
            other methods. The first item in the tuple is the page of results -
            a list or dict similar to other methods. The 2nd and 3rd items are
            cursors for making requests for newer/earlier pages, the before cursor 
            which the second item, and for making requests for older/later pages,
            the after cursor which is the 3rd item.
        
        :param str product_id: The product id whose trades are to be retrieved.
            The product id is a string consisting of a base currency and a 
            quote currency. eg., BTC-USD, ETH-EUR, etc. To see all of the 
            product ids, use :meth:`rest.Client.products`.
            
        :param int limit: (optional) The number of results to be returned per 
            request. The default (and maximum) value is 100.
            
        :param int before: (optional) The before cursor value. Used to reuest a 
            page of results newer than a previous request. This would be the 
            before cursor returned in that earlier call to this method.
        
        :param int after: (optional) The after cursor value. Used to reuest a 
            page of results older than a previous request. This would be the 
            older cursor returned in that earlier call to this method.
            
        :returns: A 3-tuple: (trades, before cursor, after cursor)
            The first item is a list of dicts representing trades for the 
            product specified. The second item is the before cursor which
            can be used in squbsequent calls to retrieve a page of results
            newer than the current one. The third item is the after cursor which 
            can be used in subsequent calls to retrieve the page of results 
            that is older than the current one. NOTE: the before cursor and after
            cursor may be None if there is not an earlier page or later page
            respectively.
        
        :Example:
        
        (
          [
            {
              'time': '2018-09-27T22:49:16.105Z', 
              'trade_id': 51584925, 
              'price': '6681.01000000', 
              'size': '0.02350019', 
              'side': 'sell'
            }, 
            {
              'time': '2018-09-27T22:49:12.39Z', 
              'trade_id': 51584924, 
              'price': '6681.00000000', 
              'size': '0.01020000', 
              'side': 'buy'
            },
            ...
          ],
          '51590012', 
          '51590010'
        )
        
        :raises ValueError: If before and after paramters are both provided.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if before and after:
            raise ValueError("before and after cannot both be provided.")  
        
        params = {'limit': limit}
        if before:
            params.update({'before': before})
        if after:
            params.update({'after': after})
            
        headers, body = await self.get('/products/{}/trades'.format(product_id),
                                       params)
        return (body, headers.get('cb-before', None), headers.get('cb-after', None))

        
    async def historic_rates(self, product_id, granularity=3600, start=None, stop=None):
        """Historic rates for a product. 
        
        Rates are returned in grouped buckets based on requested granularity.
        
        ..note:: The maximum number of data points for a single request is 300 
            candles. If your selection of start/end time and granularity will 
            result in more than 300 data points, your request will be rejected. 
            If you wish to retrieve fine granularity data over a larger time 
            range, you will need to make multiple requests with new start/end 
            ranges.
          
        ..note::  Historical rate data may be incomplete. No data is published 
            for intervals where there are no ticks.
            
        .. warning:: Historical rates should not be polled frequently. If you 
            need real-time information, use the trade and book endpoints along 
            with the websocket feed.
        
        :param str product_id: The product id whose rates are to be retrieved.
            The product id is a string consisting of a base currency and a 
            quote currency. eg., BTC-USD, ETH-EUR, etc. To see all of the 
            product ids, use :meth:`rest.Client.products`.
        
        :param int granularity: (optional) Desired timeslice in seconds. The 
            granularity field must be one of the following values: {60, 300, 
            900, 3600, 21600, 86400}. Otherwise, your request will be rejected. 
            These values correspond to timeslices representing one minute, five 
            minutes, fifteen minutes, one hour, six hours, and one day, 
            respectively. The default is 3600 (1 hour).
            
        :param str start: (optional) The start time of the requested historic 
            rates as a str in ISO 8601 format. This field is optional. If it is 
            set, then stop must be set as well If neither start nor stop are 
            set, start will default to the time relative to now() that would 
            return 300 results based on the granularity.
        
        :param str stop: (optional) The end time of the requested historic 
            rates as a str in ISO 8601 format. This field is optional. If it is 
            set then start must be set as well. If it is not set, stop will 
            default to now().
        
         .. note:: If either one of the start or end fields are not provided 
            then both fields will be ignored. If a custom time range is not 
            declared then one ending now is selected.
            
        :returns: A list of lists where each list item is a "bucket" 
            representing a timeslice of length granularity. The fields of the
            bucket are: [ time, low, high, open, close, volume ]
            
            * **time** bucket start time as a Unix timestamp
            * **low** lowest price during the bucket interval
            * **high** highest price during the bucket interval
            * **open** opening price (first trade) in the bucket interval
            * **close** closing price (last trade) in the bucket interval
            * **volume** volume of trading activity during the bucket interval
            
        :Example:
        
        [
          [1538179200, 61.12, 61.75, 61.74, 61.18, 2290.8172972700004], 
          [1538175600, 61.62, 61.8, 61.65, 61.75, 2282.2335001199995], 
          [1538172000, 61.52, 61.79, 61.66, 61.65, 3877.4680861400007],
          ...
        ]
            
        :raises ValueError: If granularity is not one of the possible values.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if granularity not in (60, 300, 900, 3600, 21600, 86400):
            raise ValueError("invalid granularity {}".format(granularity))
            
        params = {'granularity': granularity}
        
        if start and stop:
            params.update({'start': start, 'stop': stop})
            
        headers, body = await self.get('/products/{}/candles'.format(product_id),
                                       params=params)
                                       
        if start and stop:
            return [x for x in body if x[0] >= dateutil.parser.parse(start).timestamp()]
        return body

       
    async def get_24hour_stats(self, product_id):
        """Get 24 hr stats for a product.
        
        :param str product_id: The product id whose stats are to be retrieved.
            The product id is a string consisting of a base currency and a 
            quote currency. eg., BTC-USD, ETH-EUR, etc. To see all of the 
            product ids, use :meth:`rest.Client.products`.
            
        :returns: A dict of stats for the product including: open, high, low,
            volume, last price, and 30 day volume.
            
        :Example:
        
        {
          'open': '6710.37000000', 
          'high': '6786.73000000', 
          'low': '6452.02000000', 
          'volume': '9627.98224214', 
          'last': '6484.03000000', 
          'volume_30day': '238376.24964395'
        }
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/products/{}/stats'.format(product_id))
        return body

        
    async def currencies(self):
        """List known currencies.
        
        Currency codes will conform to the ISO 4217 standard where possible. 
        Currencies which have or had no representation in ISO 4217 may use a 
        custom code.
        
        ..note:: Not all currencies may be currently in use for trading.
        
        :returns: A list of dicts where each dict contains information about a
            currency.
            
        :Example:
        
        [
          {
            'id': 'BTC', 
            'name': 'Bitcoin', 
            'min_size': '0.00000001', 
            'status': 'online', 
            'message': None
          },
          ...
        ]
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/currencies')
        return body

        
    async def server_time(self):
        """Get the API server time.
        
        :returns: A dict with two fields: iso and epoch. iso is an ISO 8601 str,
            and epoch is a float. Both represent the current time at the API
            server.
            
        :Example:
        
        {
          'iso': '2018-09-29T03:02:27.753Z', 
          'epoch': 1538190147.753
        }
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/time')
        return body

        
    async def accounts(self):
        """Get a list of trading accounts.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
        
        :returns: A list of dicts where each dict contains information about
            a trading a account. The fields of the dict are:
            
        * **id** The account ID
        * **currency** Account currency
        * **balance*** Total balance
        * **available** Blalance available for use (=balance - hold)
        * **hold** Funds on hold (not available for use)
        * **profile_id**
        
        :Example:
        
        [
          {
            'id': 'a764610f-334e-4ece-b4dd-f31111ed58e7', 
            'currency': 'USD', 
            'balance': '1000.0000005931528000', 
            'available': '1000.0000005931528', 
            'hold': '0.0000000000000000', 
            'profile_id': '019be148-d490-45f9-9ead-0d1f64127716'
          },
          ...
        ]
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/accounts', auth=True)
        return body
        
    async def account(self, account_id):
        """Information for a single account. 
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        :param str account_id: The ID of the account to be retrieved.
            
        :returns: A dict of account information. The fields of the dict are:

        * **id** The account ID
        * **currency** Account currency
        * **balance*** Total balance
        * **available** Blalance available for use (=balance - hold)
        * **hold** Funds on hold (not available for use)
        * **profile_id**
        
        :Example:
        {
          'id': 'a764610f-334e-4ece-b4dd-f31111ed58e7', 
          'currency': 'USD', 
          'balance': '1000.0000005931528000', 
          'available': '1000.0000005931528', 
          'hold': '0.0000000000000000', 
          'profile_id': '019be148-d490-45f9-9ead-0d1f64127716'
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/accounts/{}'.format(account_id), auth=True)
        return body

      
    async def account_history(self, account_id, limit=100, before=None, after=None):
        """List activity for an account.account
        
        Account activity either increases or decreases your account balance. 
        Items are paginated and sorted latest first.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        .. note:: This method is paginated. Methods that can return multiple 
            pages of results return a 3-tuple instead of a dict or list like most
            other methods. The first item in the tuple is the page of results -
            a list or dict similar to other methods. The 2nd and 3rd items are
            cursors for making requests for newer/earlier pages, the before cursor 
            which the second item, and for making requests for older/later pages,
            the after cursor which is the 3rd item.
           
        :param str account_id: The id of the account whose history is to be
            retrieved.
            
        :param int limit: (optional) The number of results to be returned per 
            request. The default (and maximum) value is 100.
            
        :param int before: (optional) The before cursor value. Used to reuest a 
            page of results newer than a previous request. This would be the 
            before cursor returned in that earlier call to this method. The 
            default is None.
        
        :param int after: (optional) The after cursor value. Used to reuest a 
            page of results older than a previous request. This would be the 
            older cursor returned in that earlier call to this method. The
            default is None.
        
        :returns: A 3-tuple (history, before cursor, after cursor)
            The first item is a list of dicts each representing an instance of
            account activity. The different types of activity returned are:
            
            * **transfer** Funds moved to/from Coinbase to Coinbase Pro
            * **match** Funds moved as a result of a trade
            * **fee** Fee as a result of a trade
            * **rebate** Fee rebate
            
            The details field contains type-specific details about the specific
            transaction.
        
            The second item in the tuple is the before cursor which can be used 
            in squbsequent calls to retrieve a page of results newer than 
            the current one. The third item is the after cursor which can be 
            used in subsequent calls to retrieve the page of results that is 
            older than the current one. NOTE: the before cursor and after
            cursor may be None if there is not an earlier page or later page
            respectively.
        
        :Example:
        
        (
          [
            {
              'created_at': '2018-09-28T19:31:21.211159Z', 
              'id': 10712040275, 
              'amount': '-600.9103845810000000', 
              'balance': '0.0000005931528000', 'type': 
              'match', 
              'details': {
                           'order_id': 'd2fadbb5-8769-4b80-91da-be3d9c6bd38d', 
                           'trade_id': '34209042', 
                           'product_id': 'BTC-USD'
                         }
            }, 
            {
              'created_at': '2018-09-23T23:13:45.771507Z', 
              'id': 1065316993, 
              'amount': '-170.0000000000000000', 
              'balance': '6.7138918107528000', 
              'type': 'transfer', 
              'details': {
                           'transfer_id': 'd00841ff-c572-4726-b9bf-17e783159256', 
                           'transfer_type': 'withdraw'
                         }
            }, 
            ...
          ],
          '1071064024',
          '1008063508'
        )
        
        :raises ValueError: If ...
        
            * the client is not configured for authorization.
            * before and after are both set.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if before and after:
            raise ValueError("before and after cannot both be provided.") 
            
        params = {'limit': limit}
        if before:
            params.update({'before': before})
        if after:
            params.update({'after': after})
            
        headers, body = await self.get('/accounts/{}/ledger'.format(account_id), 
                                       params=params, auth=True)
        return (body, headers.get('cb-before', None), headers.get('cb-after', None))

        
    async def holds(self, account_id, limit=100, before=None, after=None):
        """Get any existing holds on an account.
        
        Holds are placed on an account for any active orders or pending withdraw 
        requests. As an order is filled, the hold amount is updated. If an order 
        is canceled, any remaining hold is removed. For a withdraw, once it is 
        completed, the hold is removed.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        .. note:: This method is paginated. Methods that can return multiple 
            pages of results return a 3-tuple instead of a dict or list like most
            other methods. The first item in the tuple is the page of results -
            a list or dict similar to other methods. The 2nd and 3rd items are
            cursors for making requests for newer/earlier pages, the before cursor 
            which the second item, and for making requests for older/later pages,
            the after cursor which is the 3rd item.
            
        :param str account_id: The acount ID to be checked for holds.
        
        :param int limit: (optional) The number of results to be returned per 
            request. The default (and maximum) value is 100.
        
        :param int before: (optional) The before cursor value. Used to reuest a 
            page of results newer than a previous request. This would be the 
            before cursor returned in that earlier call to this method. The 
            default is None.
        
        :param int after: (optional) The after cursor value. Used to reuest a 
            page of results older than a previous request. This would be the 
            older cursor returned in that earlier call to this method. The
            default is None.
            
        :returns: A 3-tuple (holds, before cursor, after cursor)
            The first item is a list of dicts each representing a hold on the 
            account. The fields of the dict are:
            
            * **id** The hold id
            * **acount_id** The id of the account the hold is on
            * **created_at** The date and time the hold was created
            * **updated_at** The date and time the hold was updated
            * **amount** The amount of the hold
            * **type** The reason for the hold, either **order** or **transfer**
            * **ref** The id of the order or the transfer that caused the hold
            
            The second item in the tuple is the before cursor which can be used 
            in squbsequent calls to retrieve a page of results newer than 
            the current one. The third item is the after cursor which can be 
            used in subsequent calls to retrieve the page of results that is 
            older than the current one. NOTE: the before cursor and after
            cursor may be None if there is not an earlier page or later page
            respectively.
            
        :Example:
        
        (
          [
            {
              "id": "82dcd140-c3c7-4507-8de4-2c529cd1a28f",
              "account_id": "e0b3f39a-183d-453e-b754-0c13e5bab0b3",
              "created_at": "2014-11-06T10:34:47.123456Z",
              "updated_at": "2014-11-06T10:40:47.123456Z",
              "amount": "4.23",
              "type": "order",
              "ref": "0a205de4-dd35-4370-a285-fe8fc375a273",
            },
            ...
          ],
          '1071064024',
          '1008063508'
        )
            
        :raises ValueError: If ...
        
            * the client is not configured for authorization.
            * before and after are both set.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if before and after:
            raise ValueError("before and after cannot both be provided.") 
            
        params = {'limit': limit}
        if before:
            params.update({'before': before})
        if after:
            params.update({'after': after})
            
        headers, body = await self.get('/accounts/{}/holds'.format(account_id), 
                                       params=params, auth=True)
        return (body, headers.get('cb-before', None), headers.get('cb-after', None))
        
        
    async def place_order(self, side, product_id, order_type='limit', price=None,
                          size=None, funds=None, time_in_force='GTC', 
                          cancel_after=None, post_only=True, stop=None,
                          stop_price=None, client_oid=None, stp='dc'):
        """Place a new order.
        
        You can place two types of orders: limit and market. Orders can only be 
        placed if your account has sufficient funds. Once an order is placed, 
        your account funds will be put on hold for the duration of the order. 
        How much and which funds are put on hold depends on the order type and 
        parameters specified. 
        
        ..note:: This method requires authorization. The API key must have 
            the "trade" permission.
            
        :param str side: Either buy or sell
        
        :param str product_id: The product id to be bought or sold.
            The product id is a string consisting of a base currency and a 
            quote currency. eg., BTC-USD, ETH-EUR, etc. To see all of the 
            product ids, use :meth:`rest.Client.products`.
            
        :param str order_type: The type of the order. This must be either limit
            or market. The order type you specify will influence which other 
            order parameters are required as well as how your order will be 
            executed by the matching engine. If order_type is not specified, 
            the order will default to a limit order.
            
        :param float price: For limit orders this is the price the order is to
            be executed at. This paramater may also be a string to avoid 
            floating point issues. The default is None.
            
        :param float size: For both limit and market orders this is the quantity
            of the cryptocurrency to buy or sell. This parameter may also be
            a string. The default is None
            
        :param float funds: For market orders, this is the amount of quote
            currency to be used for a purchase (buy) or the amount to be 
            obtained from a sale (sell). Either size or funds must be set
            for a market order but not both. This may also be a string. The
            default is None.
        
        :param str time_in_force: For limit orders, time in force policies 
            provide guarantees about the lifetime of an order. There are 
            four policies: good till canceled GTC, good till time GTT, immediate 
            or cancel IOC, and fill or kill FOK. The default is GTC.
            
        :param str cancel_after: The length of time before a GTT order is 
            cancelled. Must be either min, hour, or day. time_in_force must 
            be GTT or an error is raised. If cancel_after is not set for a GTT
            order, the order will be treated as GTC. The default is None.
            
        :param bool post_only: The post only flag for limit orders. It indicates 
            that the order should only make liquidity. If any part of the order 
            results in taking liquidity, the order will be rejected and no part 
            of it will execute. This flag is ignored for IOC and FOK orders. The
            default is True.
            
        :param str stop: If this is a stop order, this value must be either loss
            or entry. Requires stop_price to be set. The default is None.
            
        :param float stop_price: The trigger price for stop orders. Ignored if
            stop is not set. This may also be a string. The default is None.
            
        :param str client_oid: A self generated ID to identify the order. The
            default is None.
            
        :param str stp: Self trade preservation flag. The possible values are
            dc (decrease and cancel), co (cancel oldest), cn (cancel newest),
            or cb (cancel both). The default is dc.
            
        ..note:: To see a more detailed explanation of these parameters and to
            learn more about the order life cycle, please see the official 
            Coinbase Pro API documentation at: https://docs.gdax.com/#channels.
        
        :returns: A dict of order information.
        
        :Example:
        
        {
          'id': '5f25cced-f487-41bc-a771-e71fabf0b5ad', 
          'price': '7000.00000000', 
          'size': '0.10000000', 
          'product_id': 'BTC-USD', 
          'side': 'sell', 
          'stp': 'dc', 
          'type': 'limit', 
          'time_in_force': 'GTC', 
          'post_only': True, 
          'created_at': '2018-11-02T12:53:00.724371Z', 
          'fill_fees': '0.0000000000000000', '
          'filled_size': '0.00000000', 
          'executed_value': '0.0000000000000000', 
          'status': 'pending', 
          'settled': False
        }
        
        :raises ValueError: If... 
        
            * The client is not configured for authorization.
            * The side is not either "buy" or "sell".
            * The order_type is not either "limit" or "market".
            * If the order_type is limit and size and price are
                not set.
            * The time_in_force for a limit order is not GTC, GTT, IOC or FOK.
            * cancel_after is set for a limit order but time_in_force isn't GTT.
            * cancel_after for a limit order is set but isn't min, hour or day.
            * A market order doesn't have either funds or size set.
            * A market order has both funds and size set.
            * stop is set to something other than loss or entry.
            * A stop order does not have stop_price set.
            * stp is a value other than dc. co, cn, or cb.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        
        if side not in ('buy', 'sell'):
            raise ValueError("Invalid side: {}. Must be either buy or sell".format(side))
            
        if order_type not in ('limit', 'market'):
            raise ValueError("Invalid order type: {}. Must be either market or limit".format(order_type))
            
        if stop and stop not in ('loss', 'entry'):
            raise ValueError("Invalid stop: {}. Must be either loss or entry.".format(stop))
            
        if stop and not stop_price:
            raise ValueError("Stop orders must have stop_price set.")
            
        if stp not in ('dc', 'co', 'cn', 'cb'):
            raise ValueError('Invalid stp: {}. Must be dc, co, cn, or cb.'.format(stp))
        
        data = {
                 'side': side,
                 'product_id': product_id,
                 'order_type': order_type,
                 'stp': stp
                }
                 
        if stop:
            data.update({'stop': stop, 'stop_price': stop_price})
            
        if client_oid:
            data['client_oid'] = client_oid
                 
        if order_type == 'limit':
            
            if not (price and size):
                raise ValueError('Limit orders must have both price and size set.')
                
            if time_in_force not in ('GTC', 'GTT', 'IOC', 'FOK'):
                raise ValueError('time_in_force must be GTC, GCC, IOC or FOK.')
                
            if cancel_after and not time_in_force == 'GTT':
                raise ValueError('cancel_after requires time_in_force to be GTT')
                
            if cancel_after and cancel_after not in ('min', 'hour', 'day'):
                raise ValueError('cancel_after must be min, hour, or day')
                
            data.update({
                          'price': price,
                          'size': size,
                          'time_in_force': time_in_force,
                          'post_only': post_only
                        })
                         
            if cancel_after:
                data['cancel_after'] = cancel_after
                
        else:
            
            if not (funds or size):
                raise ValueError('Market orders must have funds or size set.')
                
            if funds and size:
                raise ValueError("Market orders can't have both funds and size set.")
                
            if size:
                data['size'] = size
                
            if funds:
                data['funds'] = funds
        
        headers, body = await self.post('/orders', data=data, auth=True)
        return body
        
    
    async def cancel(self, order_id):
        """Cancel a previously placed order.

        If the order had no matches during its lifetime its record may be 
        purged. This means the order details will not be available with 
        :meth:`rest.Client.order`.
        
        ..note:: This method requires authorization. The API key must have 
            the "trade" permission.
            
        :param str order_id: The id of the order to be cancelled. The order id 
            is the server-assigned order id and not the optional client_oid.
            
        :returns: A list which successful contains a single string entry, the
            id of the cancelled order.
            
        :Example:
        
        ["144c6f8e-713f-4682-8435-5280fbe8b2b4"]
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.delete('/orders/{}'.format(order_id), auth=True)
        
        return body
        
        
    async def cancel_all(self, product_id=None):
        """Cancel all open orders.
        
         ..note:: This method requires authorization. The API key must have 
            the "trade" permission.
            
        :param str product_id: (optional) Only cancel orders for the specified
            product. The default is None.
            
        :returns: A list of the ids of the orders that were successfully 
            cancelled.
            
        :Example:
        
        [
          "144c6f8e-713f-4682-8435-5lia280fbe8b2b4",
          "debe4907-95dc-442f-af3b-cec12f42ebda",
          "cf7aceee-7b08-4227-a76c-3858144323ab",
          "dfc5ae27-cadb-4c0c-beef-8994936fde8a",
          "34fecfbf-de33-4273-b2c6-baf8e8948be4"
        ]
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        params = {'product_id': product_id} if product_id else {}
        
        headers, body = await self.delete('/orders', params=params, auth=True)
        
        return body
        
    
    async def orders(self, status=None, product_id=None, limit=100, before=None, 
                     after=None):
        """List your current open orders. 
        
        Only open or un-settled orders are returned. As soon as an order is no 
        longer open and settled, it will no longer appear in the default 
        request.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        .. note:: This method is paginated. Methods that can return multiple 
            pages of results return a 3-tuple instead of a dict or list like most
            other methods. The first item in the tuple is the page of results -
            a list or dict similar to other methods. The 2nd and 3rd items are
            cursors for making requests for newer/earlier pages, the before cursor 
            which the second item, and for making requests for older/later pages,
            the after cursor which is the 3rd item.
            
        :param str status: (optional) Limit list of orders to these statuses: 
            open, pending, active or all. The parameter maybe a single string or a 
            list of strings to return more than one status. i.e, ['open', 'active'].
            Passing 'all' returns orders of all statuses. Note: Open orders may 
            change state between the request and the response depending on 
            market conditions.
        
        :param str product_id: (optional) Filter orders listed by product_id
        
        :param int limit: (optional) The number of results to be returned per 
            request. The default (and maximum) value is 100.
        
        :param int before: (optional) The before cursor value. Used to reuest a 
            page of results newer than a previous request. This would be the 
            before cursor returned in that earlier call to this method.
        
        :param int after: (optional) The after cursor value. Used to reuest a 
            page of results older than a previous request. This would be the 
            older cursor returned in that earlier call to this method.
            
        :returns: A list of dicts where each dict is information about an order.
        
        :returns: A 3-tuple: (orders, before cursor, after cursor)
            The first item is a list of dicts representing the orders. 
            The second item is the before cursor which can be used in squbsequent 
            calls to retrieve a page of results newer than the current one. The 
            third item is the after cursor which can be used in subsequent calls 
            to retrieve the page of results that is older than the current one. 
            NOTE: the before cursor and after cursor may be None if there is not 
            an earlier page or later page respectively.
        
        :Example:
        
        ([
          {
            "id": "d0c5340b-6d6c-49d9-b567-48c4bfca13d2",
            "price": "0.10000000",
            "size": "0.01000000",
            "product_id": "BTC-USD",
            "side": "buy",
            "stp": "dc",
            "type": "limit",
            "time_in_force": "GTC",
            "post_only": false,
            "created_at": "2016-12-08T20:02:28.53864Z",
            "fill_fees": "0.0000000000000000",
            "filled_size": "0.00000000",
            "executed_value": "0.0000000000000000",
            "status": "open",
            "settled": false
          },
          {
            "id": "8b99b139-58f2-4ab2-8e7a-c11c846e3022",
            "price": "1.00000000",
            "size": "1.00000000",
            "product_id": "BTC-USD",
            "side": "buy",
            "stp": "dc",
            "type": "limit",
            "time_in_force": "GTC",
            "post_only": false,
            "created_at": "2016-12-08T20:01:19.038644Z",
            "fill_fees": "0.0000000000000000",
            "filled_size": "0.00000000",
            "executed_value": "0.0000000000000000",
            "status": "open",
            "settled": false
          }
         ],
         '1071064024',
         '1008063508'
        )
        
        :raises ValueError: If ... 
        
            * the client is not configured for authorization.
            * an invalid status string is provided.
            * before and after are both set.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if before and after:
            raise ValueError("before and after cannot both be provided.") 
        
        params = CIMultiDict({'limit': limit})
        if before:
            params.update({'before': before})
        if after:
            params.update({'after': after})
        
        if status:
            if isinstance(status, str):
                status = [status]
                
            for value in status:
                if value not in ('active', 'all', 'open', 'pending'):
                    raise ValueError("Invalid status: {}".format(value))
               
            params.update([('status', value) for value in status])
            
        if product_id:
            params['product_id'] = product_id
                    
        headers, body = await self.get('/orders', params=params, auth=True)
        
        return (body, headers.get('cb-before', None), headers.get('cb-after', None))
        
        
    async def order(self, order_id):
        """Get a single order by order id.

        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        :param str order_id: The id of the order to be retrieved.
        
        :returns: A dict of information about the order.
        
        :Example:
        
        {
          "id": "68e6a28f-ae28-4788-8d4f-5ab4e5e5ae08",
          "size": "1.00000000",
          "product_id": "BTC-USD",
          "side": "buy",
          "stp": "dc",
          "funds": "9.9750623400000000",
          "specified_funds": "10.0000000000000000",
          "type": "market",
          "post_only": false,
          "created_at": "2016-12-08T20:09:05.508883Z",
          "done_at": "2016-12-08T20:09:05.527Z",
          "done_reason": "filled",
          "fill_fees": "0.0249376391550000",
          "filled_size": "0.01291771",
          "executed_value": "9.9750556620000000",
          "status": "done",
          "settled": true
        }
        
        ..note:: Open orders may change state between the request and the 
            response depending on market conditions.
            
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/orders/{}'.format(order_id), auth=True)
        
        return body
        
        
    async def fills(self, order_id='', product_id='', limit=100, before=None, 
                    after=None):
        """Get a list of recent fills.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        .. note:: This method is paginated. Methods that can return multiple 
            pages of results return a 3-tuple instead of a dict or list like most
            other methods. The first item in the tuple is the page of results -
            a list or dict similar to other methods. The 2nd and 3rd items are
            cursors for making requests for newer/earlier pages, the before cursor 
            which the second item, and for making requests for older/later pages,
            the after cursor which is the 3rd item.
            
        :param str order_id: (optional) Limit list of fills to this order_id
        
        :param str product_id: (optional) Limit list of fills to this product_id
        
        .. note:: Either order_id or product_id must be defined but not both.
        
        :param int limit: (optional) The number of results to be returned per 
            request. The default (and maximum) value is 100.
        
        :param int before: (optional) The before cursor value. Used to reuest a 
            page of results newer than a previous request. This would be the 
            before cursor returned in that earlier call to this method.
        
        :param int after: (optional) The after cursor value. Used to reuest a 
            page of results older than a previous request. This would be the 
            older cursor returned in that earlier call to this method.
        
        :returns: A list of dicts representing the fills.
        
        :Example:
        
        [
          {
            "trade_id": 74,
            "product_id": "BTC-USD",
            "price": "10.00",
            "size": "0.01",
            "order_id": "d50ec984-77a8-460a-b958-66f114b0de9b",
            "created_at": "2014-11-07T22:19:28.578544Z",
            "liquidity": "T",
            "fee": "0.00025",
            "settled": true,
            "side": "buy"
          },
          ...,
        ]
        
        :raises ValueError: If... 
            
            * the client is not configured for authorization.
            * before and after are both set.
            * neither order_id nor product_id are defined or if both are defined.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if before and after:
            raise ValueError("before and after cannot both be provided.") 
            
        if not order_id and not product_id:
            raise ValueError("Either order_id or product_id must be defined.")
            
        if order_id and product_id:
            raise ValueError("order_id or product_id cannot both be sent.")
            
        params = CIMultiDict({'limit': limit})
        if before:
            params['before'] = before
        if after:
            params['after'] = after
        if order_id:
            params['order_id'] = order_id
        if product_id:
            params['product_id'] = product_id
            
        headers, body = await self.get('/fills', params=params, auth=True)
    
        return (body, headers.get('cb-before', None), headers.get('cb-after', None))
        
        
    async def payment_methods(self):
        """Get a list of your payment methods.

        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :returns: A list of dicts where each dict contains detailed information
            about a payment method the account has available.
            
        :Example:
        
        [
            {
                "id": "bc6d7162-d984-5ffa-963c-a493b1c1370b",
                "type": "ach_bank_account",
                "name": "Bank of America - eBan... ********7134",
                "currency": "USD",
                "primary_buy": true,
                "primary_sell": true,
                "allow_buy": true,
                "allow_sell": true,
                "allow_deposit": true,
                "allow_withdraw": true,
                "limits": {
                    "buy": [
                        {
                            "period_in_days": 1,
                            "total": {
                                "amount": "10000.00",
                                "currency": "USD"
                            },
                            "remaining": {
                                "amount": "10000.00",
                                "currency": "USD"
                            }
                        }
                    ],
                    "instant_buy": [
                        {
                            "period_in_days": 7,
                            "total": {
                                "amount": "0.00",
                                "currency": "USD"
                            },
                            "remaining": {
                                "amount": "0.00",
                                "currency": "USD"
                            }
                        }
                    ],
                    "sell": [
                        {
                            "period_in_days": 1,
                            "total": {
                                "amount": "10000.00",
                                "currency": "USD"
                            },
                            "remaining": {
                                "amount": "10000.00",
                                "currency": "USD"
                            }
                        }
                    ],
                    "deposit": [
                        {
                            "period_in_days": 1,
                            "total": {
                                "amount": "10000.00",
                                "currency": "USD"
                            },
                            "remaining": {
                                "amount": "10000.00",
                                "currency": "USD"
                            }
                        }
                    ]
                }
            },
        ]
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/payment-methods', auth=True)
        return body
        
    
    async def coinbase_accounts(self):
        """Get a list of your coinbase accounts.

        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :returns: A list of dicts where each dict contains information about a
            Coinbase account.
            
        :Example:
        
        [
            {
                "id": "fc3a8a57-7142-542d-8436-95a3d82e1622",
                "name": "ETH Wallet",
                "balance": "0.00000000",
                "currency": "ETH",
                "type": "wallet",
                "primary": false,
                "active": true
            },
            {
                "id": "2ae3354e-f1c3-5771-8a37-6228e9d239db",
                "name": "USD Wallet",
                "balance": "0.00",
                "currency": "USD",
                "type": "fiat",
                "primary": false,
                "active": true,
                "wire_deposit_information": {
                    "account_number": "0199003122",
                    "routing_number": "026013356",
                    "bank_name": "Metropolitan Commercial Bank",
                    "bank_address": "99 Park Ave 4th Fl New York, NY 10016",
                    "bank_country": {
                        "code": "US",
                        "name": "United States"
                    },
                    "account_name": "Coinbase, Inc",
                    "account_address": "548 Market Street, #23008, San Francisco, CA 94104",
                    "reference": "BAOCAEUX"
                }
            },
            {
                "id": "1bfad868-5223-5d3c-8a22-b5ed371e55cb",
                "name": "BTC Wallet",
                "balance": "0.00000000",
                "currency": "BTC",
                "type": "wallet",
                "primary": true,
                "active": true
            },
            {
                "id": "2a11354e-f133-5771-8a37-622be9b239db",
                "name": "EUR Wallet",
                "balance": "0.00",
                "currency": "EUR",
                "type": "fiat",
                "primary": false,
                "active": true,
                "sepa_deposit_information": {
                    "iban": "EE957700771001355096",
                    "swift": "LHVBEE22",
                    "bank_name": "AS LHV Pank",
                    "bank_address": "Tartu mnt 2, 10145 Tallinn, Estonia",
                    "bank_country_name": "Estonia",
                    "account_name": "Coinbase UK, Ltd.",
                    "account_address": "9th Floor, 107 Cheapside, London, EC2V 6DN, United Kingdom",
                    "reference": "CBAEUXOVFXOXYX"
                }
            },
        ]
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/coinbase-accounts', auth=True)
        
        return body
        
    
    async def deposit_payment_method(self, amount, currency, payment_method_id):
        """Deposit funds from a payment method.
        
        To get a list of available payment methods, use 
        :meth:`rest.Client.payment_methods`.
        
        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :param float amount: The amount of the currency to deposit. This 
            paramater may also be a string to avoid floating point issues.
        
        :param str currency: The type of currency to deposit. i.e., 'USD',
            'EUR', etc.
        
        :param str payment_method_id: The id of the payment method on file to
            use. To get a list of available payment methods, use:
            :meth:`rest.Client.payment_methods`.
            
        :returns: A dict with a deposit id, timestamp and other deposit information.
        
        :Example:
        
        {
            "id": "593533d2-ff31-46e0-b22e-ca754147a96a",
            "amount": "10.00",
            "currency": "USD",
            "payout_at": "2016-08-20T00:31:09Z"
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.post('/deposits/payment-method', 
                                        data={'amount': amount,
                                              'currency': currency,
                                              'payment_method_id': payment_method_id},
                                        auth=True)
        return body
        
        
    async def deposit_coinbase(self, amount, currency, coinbase_account_id):
        """Deposit funds from a coinbase account.
        
        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :param float amount: The amount of the currency to deposit. This 
            paramater may also be a string to avoid floating point issues.
        
        :param str currency:  The type of currency to deposit. i.e., 'BTC',
            'LTC', 'USD', etc.
            
        :param str coinbase_account_id:  The id of the Coinbase account to
            deposit from. To get a list of Coinbase accounts, use:
            :meth:`rest.Client.coinbase_accounts`.
        
        :returns: A dict with a deposit id, and confirmation of the deposit 
            amount and currency.
        
        :Example:
        
        {
            "id": "593533d2-ff31-46e0-b22e-ca754147a96a",
            "amount": "10.00",
            "currency": "BTC",
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.post('/deposits/coinbase-account', 
                                data={'amount': amount,
                                      'currency': currency,
                                      'coinbase_account_id': coinbase_account_id},
                                auth=True)
        return body
        
        
    async def withdraw_payment_method(self, amount, currency, payment_method_id):
        """Withdraw funds to a payment method.
        
        To get a list of available payment methods, use 
        :meth:`rest.Client.payment_methods`.
        
        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :param float amount: The amount of the currency to withdrawal. This 
            paramater may also be a string to avoid floating point issues.
        
        :param str currency: The type of currency to withdrawal. i.e., 'USD',
            'EUR', etc.
        
        :param str payment_method_id: The id of the payment method on file to
            use. To get a list of available payment methods, use:
            :meth:`rest.Client.payment_methods`.
            
        :returns: A dict with a withdrawal id, timestamp and other deposit 
            information.
            
        :Example:
        
        {
            "id":"593533d2-ff31-46e0-b22e-ca754147a96a",
            "amount": "10.00",
            "currency": "USD",
            "payout_at": "2016-08-20T00:31:09Z"
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.post('/withdrawals/payment-method', 
                        data={'amount': amount,
                              'currency': currency,
                              'payment_method_id': payment_method_id},
                        auth=True)
        return body

        
    async def withdraw_coinbase(self, amount, currency, coinbase_account_id):
        """Withdraw funds to a coinbase account.
        
        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :param float amount: The amount of the currency to withdraw. This 
            paramater may also be a string to avoid floating point issues.
        
        :param str currency:  The type of currency to withdrawal. i.e., 'BTC',
            'LTC', 'USD', etc.
            
        :param str coinbase_account_id:  The id of the Coinbase account to
            withdraw to. To get a list of Coinbase accounts, use:
            :meth:`rest.Client.coinbase_accounts`.
        
        :returns: A dict with the withdrawal id, and confirmation of the withdrawl 
            amount and currency.
        
        :Example:
        
        {
            "id":"593533d2-ff31-46e0-b22e-ca754147a96a",
            "amount":"10.00",
            "currency": "BTC",
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.post('/withdrawals/coinbase-account', 
                                data={'amount': amount,
                                      'currency': currency,
                                      'coinbase_account_id': coinbase_account_id},
                                auth=True)
        return body
        
        
    async def withdraw_crypto(self, amount, currency, crypto_address):
        """Withdraw funds to a crypto address.
        
        ..note:: This method requires authorization. The API key must have 
            the "transfer" permission.
            
        :param float amount: The amount of the currency to withdraw. This 
            paramater may also be a string to avoid floating point issues.
        
        :param str currency:  The type of currency to withdrawal. i.e., 'BTC',
            'LTC', 'USD', etc.
            
        :param str crypto_address: The crypto address of the recipient.
        
        :returns: A dict with the withrawal id, and confirmation of the withdrawl 
            amount and currency.
        
        :Example:
        
            {
                "id":"593533d2-ff31-46e0-b22e-ca754147a96a",
                "amount":"10.00",
                "currency": "BTC",
            }
            
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.post('/withdrawals/crypto', 
                                data={'amount': amount,
                                      'currency': currency,
                                      'crypto_address': crypto_address},
                                auth=True)
        return body        

        
    async def stablecoin_conversion(self, from_currency_id, to_currency_id, amount):
        """Convert to and from a stablecoin.
        
        ..note:: This method requires authorization. The API key must have 
            the "trade" permission.
        
        ..note:: As oF November 8th, 1018, Coinbase Pro only supports
            USD-USDC conversions
        
        :param str from_currency_id: The id of the currency to convert from.
        
        :param str to_currency_id: The id of the currency to convert to.
        
        :param float amount: The amount of currency to convert. This 
            paramater may also be a string to avoid floating point issues.
        
        :returns: A dict summarizing the conversion.
        
        :Example:
        
        {
            "id": "8942caee-f9d5-4600-a894-4811268545db",
            "amount": "10000.00",
            "from_account_id": "7849cc79-8b01-4793-9345-bc6b5f08acce",
            "to_account_id": "105c3e58-0898-4106-8283-dc5781cda07b",
            "from": "USD",
            "to": "USDC"
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.post('/conversions', 
                                data={'from_currency_id': from_currency_id,
                                      'to_currency_id': to_currency_id,
                                      'amount': amount},
                                auth=True)
        return body
        
        
    async def create_report(self, report_type, start_date, end_date, 
                            product_id='', account_id='', report_format='pdf',
                            email=''):
        """Create a report about your account history.
        
        Reports provide batches of historic information about your account in 
        various human and machine readable forms.
        
        The report will be generated when resources are available. Report status 
        can be queried via :meth:`rest.Client.report_status`. The a url for
        the report file will be available once the report has successfully been 
        created and is available for download.
        
        ..note:: Reports are only available for download for a few days after 
            being created. Once a report expires, the report is no longer 
            available for download and is deleted.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        :param str report_type: The type of report to generate. This must be
            either "fills" or "account".
            
        :param str start_date: The starting date of the requested report as a 
            str in ISO 8601 format.
            
        :param str end_date: The ending date of the requested report as a 
            str in ISO 8601 format.
            
        :param str product_id: (optional) ID of the product to generate a fills 
            report for. E.g. BTC-USD. Required if type is fills.
            
        :param str account_id: (optional) ID of the account to generate an 
            account report for. Required if type is account.
            
        :param str report_format: (optional) Format of the report to be 
            generated. Can be either pdf or csv. The default is pdf.
            
        :param str email: (optional) Email address to send the report to. The 
            default is None.
            
        :returns: A dict of information about the report including its id which
            will be needed to check its status.
            
        :Example:
        
        {
            "id": "0428b97b-bec1-429e-a94c-59232926778d",
            "type": "fills",
            "status": "pending",
            "created_at": "2015-01-06T10:34:47.000Z",
            "completed_at": undefined,
            "expires_at": "2015-01-13T10:35:47.000Z",
            "file_url": undefined,
            "params": {
                "start_date": "2014-11-01T00:00:00.000Z",
                "end_date": "2014-11-30T23:59:59.000Z"
            }
        }    
            
        :raises ValueError: If ... 
            * the client is not configured for authorization.
            * invalid report_type provided.
            * report_type is fills and product_id is not provided.
            * report_type is account and account_id is not provided.
            * invalid report_format provided.
            
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        if report_type not in ("account", "fills"):
            raise ValueError(
                "Invalid report_type: {}. Must be 'fills' or 'account'.".format(
                    report_type))
        
        if report_type == 'fills' and not product_id:
            raise ValueError("product_id must be defined for report_type fills.")
            
        if report_type == 'account' and not account_id:
            raise ValueError("account_id must be defined for report_type account.")
            
        if report_format not in ('csv', 'pdf'):
            raise ValueError(
                "Invalid format {}. Must be either 'csv' or 'pdf'.".format(report_format))
            
        data = {
                'report_type': report_type,
                'start_date': start_date,
                'end_date': end_date,
                'report_format': report_format
               }
               
        if product_id:
            data['product_id'] = product_id
            
        if account_id:
            data['account_id'] = account_id
            
        if email:
            data['email'] = email
        
        headers, body = await self.post('/reports', data=data, auth=True)
        
        return body
        
        
    async def report_status(self, report_id):
        """Get the status of a report.
        
        Once a report request has been accepted for processing, the status is 
        available by polling the report resource endpoint.
        
        The possible status values are:
        
            * **pending** - The report request has been accepted and is awaiting 
                processing.
            * **creating** - The report is being created.
            * **ready** - The report is ready for download from file_url.
            
        The final report will be uploaded and available at file_url once the 
        status indicates ready.
        
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        :param str report_id: The id of the report. This is obtained from
            :meth:`rest.Client.create_report`.
            
        :returns: A dict summarizing the current status of the report.
        
        :Example:
        
        **Creating report**
        
        {
            "id": "0428b97b-bec1-429e-a94c-59232926778d",
            "type": "fills",
            "status": "creating",
            "created_at": "2015-01-06T10:34:47.000Z",
            "completed_at": undefined,
            "expires_at": "2015-01-13T10:35:47.000Z",
            "file_url": undefined,
            "params": {
                "start_date": "2014-11-01T00:00:00.000Z",
                "end_date": "2014-11-30T23:59:59.000Z"
            }
        }
        
        
        **Finished report**
        
        {
            "id": "0428b97b-bec1-429e-a94c-59232926778d",
            "type": "fills",
            "status": "ready",
            "created_at": "2015-01-06T10:34:47.000Z",
            "completed_at": "2015-01-06T10:35:47.000Z",
            "expires_at": "2015-01-13T10:35:47.000Z",
            "file_url": "https://example.com/0428b97b.../fills.pdf",
            "params": {
                "start_date": "2014-11-01T00:00:00.000Z",
                "end_date": "2014-11-30T23:59:59.000Z"
            }
        }
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/reports/{}'.format(report_id), auth=True)
        
        return body
        
        
    async def trailing_volume(self):
        """Return your 30-day trailing volume for all products.
        
         This is a cached value that’s calculated every day at midnight UTC.
         
        ..note:: This method requires authorization. The API key must have 
            either the "view" or "trade" permission.
            
        :returns: A list of dicts where each dict contains information about
            a specific product that was traded.
            
        :Example:
        
        [
            {
                "product_id": "BTC-USD",
                "exchange_volume": "11800.00000000",
                "volume": "100.00000000",
                "recorded_at": "1973-11-29T00:05:01.123456Z"
            },
            {
                "product_id": "LTC-USD",
                "exchange_volume": "51010.04100000",
                "volume": "2010.04100000",
                "recorded_at": "1973-11-29T00:05:02.123456Z"
            }
        ]
        
        :raises ValueError: If the client is not configured for authorization.
        
        :raises APIRequestError: For any error generated by the Coinbase Pro
            API server.
        """
        headers, body = await self.get('/users/self/trailing-volume', auth=True)
        
        return body
    
    
if __name__ == '__main__':
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    KEY = os.getenv("KEY")
    SECRET = os.getenv("SECRET")
    PASSPHRASE = os.getenv("PASSPHRASE")
    
    loop = asyncio.get_event_loop()
    
    #client = Client(loop, auth=True, key=KEY, secret=SECRET, passphrase=PASSPHRASE)
    
    async def go():
        async with Client(loop, auth=True, key=KEY, secret=SECRET, passphrase=PASSPHRASE) as client:
            headers, body = await client.get('/fail', auth=True)
            print(headers)
            print(body)
        
    loop.run_until_complete(go())
    loop.run_until_complete(client.close())
    
    loop.close()
        
        
    