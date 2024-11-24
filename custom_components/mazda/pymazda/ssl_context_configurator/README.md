# SSL Context Configurator

> [!CAUTION]
> This library relies on CPython internals. Use at your own discretion.

Python's `SSLContext` object – typical in HTTPS connections – is basically a wrapper around the OpenSSL struct `SSL_CTX`.  
Unfortunately, Python does not allow the full SSL/TLS configuration power offered by OpenSSL.

Through some _ctypes_ fun, this library finds the underlying `SSL_CTX` C object in memory, and configures it by calling the OpenSSL function `SSL_CONF_cmd`.

## Prerequisites

- CPython 3.2+ or 2.7.9+
- A copy of LibSSL (preferably the one used by CPython)

## Usage example

This library may be used, for example, to set the supported signature algorithms in an HTTPS connection:

```python
import urllib3
from ssl_context_configurator import SSLContextConfigurator

ssl_context = urllib3.util.ssl_.create_urllib3_context()

with SSLContextConfigurator(ssl_context, libssl_path='libssl.so') as ssl_context_configurator:
    ssl_context_configurator.configure_signature_algorithms('ECDSA+SHA256')

pool_manager = urllib3.PoolManager(cert_reqs='CERT_NONE', ssl_context=ssl_context)
pool_manager.request('GET', 'https://github.com/')
```

For the exhaustive configuration capabilities, consult `SSL_CONF_cmd(3)`.
