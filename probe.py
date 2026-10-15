"""Measure IPv4 TCP connect() results and publish them to Redis."""

import argparse
import json
import os
import socket
import time
from datetime import datetime, timezone

from redis import Redis
from redis.exceptions import RedisError


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
EVENT_CHANNEL = "tcp-probe-events"
TARGET_HOST = os.getenv("TARGET_HOST", "target")
TARGET_PORT = int(os.getenv("TARGET_PORT", "5000"))
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "3"))
PROBE_INTERVAL = float(os.getenv("PROBE_INTERVAL", "3"))


def check_tcp(host, port, timeout):
    started = time.perf_counter()
    status = "error"
    detail = "알 수 없는 오류가 발생했습니다."

    try:
        # AF_INET/SOCK_STREAM은 IPv4 TCP 연결을 뜻한다.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect((host, port))
        status = "open"
        detail = "TCP 연결이 성공했습니다."
    except ConnectionRefusedError:
        status = "refused"
        detail = "연결이 거부되었습니다. 포트 리스너와 거부 정책을 확인하세요."
    except socket.timeout:
        status = "timeout"
        detail = "설정한 시간 안에 TCP 연결이 완료되지 않았습니다."
    except OSError as error:
        detail = f"운영체제 오류 ({type(error).__name__}): {error}"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": f"{host}:{port}",
        "status": status,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "detail": detail,
    }


def main():
    parser = argparse.ArgumentParser(description="Publish TCP connection results")
    parser.add_argument("--once", action="store_true", help="run one probe")
    args = parser.parse_args()

    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        while True:
            event = check_tcp(TARGET_HOST, TARGET_PORT, CONNECT_TIMEOUT)
            payload = json.dumps(event, ensure_ascii=False)
            try:
                subscribers = client.publish(EVENT_CHANNEL, payload)
                print(f"[PROBE] {payload} subscribers={subscribers}", flush=True)
            except RedisError as error:
                # 전달에 실패해도 실제 TCP 검사 결과를 로그에 남긴다.
                print(
                    f"[PROBE] Redis publish failed: {error}. "
                    f"Undelivered TCP result: {payload}",
                    flush=True,
                )
                if args.once:
                    return 1

            if args.once:
                return 0
            time.sleep(PROBE_INTERVAL)
    except KeyboardInterrupt:
        print("\n[PROBE] Stopped", flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
