# -*- coding: utf-8 -*-
"""Asynchronous WebSocket client for the Coinbase Pro platform.

"""

import asyncio
import json
import logging
from urllib.parse import urlparse

from autobahn.asyncio.websocket import WebSocketClientFactory
from autobahn.asyncio.websocket import WebSocketClientProtocol

logger = logging.getLogger(__name__)

FEED_URL = 'wss://ws-feed.gdax.com'
SANDBOX_FEED_URL = 'wss://ws-feed-public.sandbox.gdax.com'


class Channel:
    """A WebSocket channel.

    A Channel object encapsulates the Coinbase Pro WebSocket channel name
    *and* one or more Coinbase Pro product ids.

    To read about Coinbase Pro channels and the data they return, visit:
    https://docs.gdax.com/#channels

    Attributes:
        name (str): The name of the WebSocket channel.
        product_ids (set of str): Set of product ids for the channel.

    """

    def __init__(self, name, product_ids):
        """Channel __init__ method.

        Args:
            name (str): The name of the WebSocket channel. Possible values
                are heatbeat, ticker, level2, full, matches, or user

            product_ids (str or list of str): A single product id
                (eg., 'BTC-USD') or list of product ids (eg., ['BTC-USD',
                'ETH-EUR', 'LTC-BTC'])

        Raises:
            ValueError: If name not valid or product ids is empty.
        """
        self.name = name.lower()
        if self.name not in ('heartbeat', 'ticker', 'level2',
                             'full', 'matches', 'user'):
            raise ValueError("invalid name {}".format(name))

        if not product_ids:
            raise ValueError("must include at least one product id")

        if not isinstance(product_ids, list):
            product_ids = [product_ids]
        self.product_ids = set(product_ids)

    def __call__(self):
        return self

    def as_dict(self):
        """Returns the Channel as a dictionary.

        Returns:
            dict: The Channel as a dict with keys name & product_ids.
        """
        return {'name': self.name, 'product_ids': list(self.product_ids)}


class ClientProtocol(WebSocketClientProtocol):
    """Websocket client protocol.

    This is a subclass of autobahn.asyncio.WebSocket.WebSocketClientProtocol.
    In most cases this should not need to be subclassed or even accessed
    directly.
    """

    def onOpen(self):
        """Callback fired on initial WebSocket opening handshake completion.

        You now can send and receive WebSocket messages.
        """
        self.factory.on_open()

    def onMessage(self, payload, isBinary):
        """Callback fired when a complete WebSocket message was received.

        Args:
            payload (bytes): The WebSocket message received.
            isBinary (bool): Flag indicating whether payload is binary or UTF-8
            encoded text.
        """
        msg = json.loads(payload.decode('utf8'))
        self.factory.on_message(msg)


class Client(WebSocketClientFactory):
    """Asyncronous WebSocket client for Coinbase Pro.

       Attributes:
           feed_url (str): The url of the WebSocket server.
    """

    def __init__(self, loop, channels, feed_url=FEED_URL,
                 name='WebSocket Client'):
        """ Client initialization.

        Args:
            loop (asyncio loop): The asyncio loop that the client runs in.
            channels (Channel or list of Channel): The initial channels to
                subscribe to.
            feed_url (str): The url of the WebSocket server. The defualt is
                copra.WebSocket.FEED_URL (wss://ws-feed.gdax.com)
            name (str): A name to identify this client in logging, etc.
        """
        self.loop = loop
        if not isinstance(channels, list):
            channels = [channels]

        self._initial_channels = channels
        self.feed_url = feed_url
        self.name = name

        self.channels = {}

        super().__init__(self.feed_url)

    def add_as_task_to_loop(self, loop):
        """Add the client to the asyncio loop.

        Creates a coroutine for making a connection to the WebSocket server and
        adds it as a task to the asyncio loop.

        Args:
            loop (asyncio event loop): The event loop that the WebSocket client
                runs in.
        """
        self.protocol = ClientProtocol()
        url = urlparse(self.url)
        self.coro = self.loop.create_connection(self, url.hostname, url.port,
                                                ssl=(url.scheme == 'wss'))
        self.loop.create_task(self.coro)

    def on_open(self):
        """Callback fired on initial WebSocket opening handshake completion.

        The WebSocket is open. This method sends the subscription message to
        the server.
        """


if __name__ == '__main__':

    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler())

    loop = asyncio.get_event_loop()

    ws = Client(loop, [Channel('heartbeat', 'BTC-USD')])
    ws.add_as_task_to_loop()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(ws.disconnect())
        loop.close()
