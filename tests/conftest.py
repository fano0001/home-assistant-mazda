# tests/conftest.py
print(">>> USING custom tests/conftest.py <<<")
try:
    from pytest_socket import disable_socket, socket_allow_hosts, socket_allow_unix_socket
    # Alles blocken...
    disable_socket()
    # ...aber UNIX-Sockets für die Event-Loop erlauben
    socket_allow_unix_socket()
    # ...und Loopback für aiohttp_server erlauben
    socket_allow_hosts(["127.0.0.1", "localhost"])
except Exception:
    # Falls das Plugin fehlt, Tests trotzdem laufen lassen
    pass
