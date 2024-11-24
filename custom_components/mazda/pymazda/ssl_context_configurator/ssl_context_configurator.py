import ctypes

from .cpython_hacks import get_raw_ssl_context

OPENSSL_SSL_CONF_FLAG_FILE = 0x2
OPENSSL_SSL_CONF_FLAG_CLIENT = 0x4
OPENSSL_SSL_CONF_FLAG_SERVER = 0x8
OPENSSL_SSL_CONF_CMD_SUCCESS = 2


class SSLContextConfiguratorLibsslError(Exception):
    pass


class SSLContextConfigurator(object):
    def __init__(self, ssl_context, libssl_path):
        self._libssl = ctypes.CDLL(libssl_path)

        self._raw_ssl_context = get_raw_ssl_context(ssl_context)

    def __enter__(self):
        self._libssl.SSL_CONF_CTX_new.restype = ctypes.c_void_p
        self._conf_ctx_ptr = ctypes.c_void_p(self._libssl.SSL_CONF_CTX_new())
        if not self._conf_ctx_ptr:
            raise SSLContextConfiguratorLibsslError('SSL_CONF_CTX_new failed.')

        self._libssl.SSL_CONF_CTX_set_flags(self._conf_ctx_ptr,
                                            OPENSSL_SSL_CONF_FLAG_FILE
                                            | OPENSSL_SSL_CONF_FLAG_CLIENT
                                            | OPENSSL_SSL_CONF_FLAG_SERVER)

        self._libssl.SSL_CONF_CTX_set_ssl_ctx(self._conf_ctx_ptr,
                                              ctypes.c_void_p(self._raw_ssl_context))

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._libssl.SSL_CONF_CTX_free(self._conf_ctx_ptr)

        return False

    def _ssl_conf_cmd(self, cmd, value):
        ssl_conf_cmd_result = self._libssl.SSL_CONF_cmd(self._conf_ctx_ptr,
                                                        bytes(cmd, encoding='ascii'),
                                                        bytes(value, encoding='ascii'))
        if ssl_conf_cmd_result != OPENSSL_SSL_CONF_CMD_SUCCESS:
            raise SSLContextConfiguratorLibsslError(
                    'SSL_CONF_cmd returned {}'.format(ssl_conf_cmd_result))

    def configure_cipher_suite(self, cipher_suite):
        self._ssl_conf_cmd('CipherString', cipher_suite)

    def configure_certificate(self, certificate):
        self._ssl_conf_cmd('Certificate', certificate)

    def configure_private_key(self, private_key):
        self._ssl_conf_cmd('PrivateKey', private_key)

    def configure_chain_ca_file(self, chain_ca_file):
        self._ssl_conf_cmd('ChainCAFile', chain_ca_file)

    def configure_chain_ca_path(self, chain_ca_path):
        self._ssl_conf_cmd('ChainCAPath', chain_ca_path)

    def configure_verify_ca_file(self, verify_ca_file):
        self._ssl_conf_cmd('VerifyCAFile', verify_ca_file)

    def configure_verify_ca_path(self, verify_ca_path):
        self._ssl_conf_cmd('VerifyCAPath', verify_ca_path)

    def configure_server_info_file(self, server_info_file):
        self._ssl_conf_cmd('ServerInfoFile', server_info_file)

    def configure_dh_parameters(self, dh_parameters):
        self._ssl_conf_cmd('DHParameters', dh_parameters)

    def configure_no_renegotiation(self):
        self._ssl_conf_cmd('NoRenegotiation', 0)

    def configure_signature_algorithms(self, signature_algorithms):
        self._ssl_conf_cmd('SignatureAlgorithms', signature_algorithms)

    def configure_client_signature_algorithms(self, client_signature_algorithms):
        self._ssl_conf_cmd('ClientSignatureAlgorithms', client_signature_algorithms)

    def configure_curves(self, curves):
        self._ssl_conf_cmd('Curves', curves)

    def configure_min_protocol(self, min_protocol):
        self._ssl_conf_cmd('MinProtocol', min_protocol)

    def configure_max_protocol(self, max_protocol):
        self._ssl_conf_cmd('MaxProtocol', max_protocol)

    def configure_protocol(self, protocol):
        self._ssl_conf_cmd('Protocol', protocol)

    def configure_options(self, options):
        self._ssl_conf_cmd('Options', options)

    def configure_verify_mode(self, verify_mode):
        self._ssl_conf_cmd('VerifyMode', verify_mode)

    def configure_client_ca_file(self, client_ca_file):
        self._ssl_conf_cmd('ClientCAFile', client_ca_file)

    def configure_client_ca_path(self, client_ca_path):
        self._ssl_conf_cmd('ClientCAPath', client_ca_path)
