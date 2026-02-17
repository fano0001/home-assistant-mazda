import ctypes
import sys


def _get_address_of_object(pyobject):
    """
    Return the memory address of a given Python object.
    CPython guarantees that id() returns that address.
    """
    return id(pyobject)


def _get_size_of_pyobject_head():
    """
    Return the size of the struct PyObject_HEAD in bytes.
    """
    return sys.getsizeof(object())


def _dereference_ptr(address, pointed_type):
    """
    Retrieve the value of the given type from the given address.
    """
    type_p = ctypes.POINTER(pointed_type)
    address_contents = ctypes.cast(address, type_p).contents
    return address_contents.value


def get_raw_ssl_context(py_ssl_context):
    """
    Return a pointer to OpenSSL's SSL_CTX struct.
    Relies on the assumption that the struct implementing Python's SSLContext objects
    is laid out as follows:
    typedef struct {
        PyObject_HEAD
        SSL_CTX *ctx;
        ...
    } PySSLContext;
    """
    raw_ssl_context_ptr_ptr = _get_address_of_object(py_ssl_context) + _get_size_of_pyobject_head()
    return _dereference_ptr(raw_ssl_context_ptr_ptr, ctypes.c_void_p)
