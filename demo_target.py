"""Small persistent TCP listener used as a known-good probe target."""

import os
import socket


HOST = "0.0.0.0"  # Docker의 다른 컨테이너에서도 연결할 수 있게 한다.
PORT = int(os.getenv("TARGET_PORT", "5000"))


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"[TARGET] Listening on {HOST}:{PORT}", flush=True)

        try:
            while True:
                connection, address = server.accept()
                with connection:
                    print(f"[TARGET] Accepted {address[0]}:{address[1]}", flush=True)
        except KeyboardInterrupt:
            print("\n[TARGET] Stopped", flush=True)


if __name__ == "__main__":
    main()
