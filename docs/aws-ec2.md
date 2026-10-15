# AWS EC2 배포 실습 (선택 사항)

이 문서는 로컬에서 재현할 수 있도록 구성한 WebSocket·Redis·Docker Compose 프로젝트를 **Ubuntu EC2 한 대**에 올려 보는 절차다. 프로젝트가 이미 Docker나 AWS에서 실행·검증되었다는 뜻은 아니다. AWS 계정, 도메인, 비용 확인이 필요하며, 실제 배포 후 관찰한 결과만 포트폴리오에 기록한다.

## 1. 배포 구조와 포트

```text
브라우저 (https://, wss://)
    │ TCP 443 (개인 접속); 인증서 HTTP-01 검증·리다이렉트는 TCP 80
    ▼
인터넷 → VPC Internet Gateway → EC2 Security Group
    ▼
Ubuntu EC2의 Docker Compose
    ├── Caddy :80/:443 ──┬── web_a:8000 (컨테이너 내부)
    │                    └── web_b:8000 (컨테이너 내부)
    ├── Redis:6379 ───────► web_a / web_b (같은 이벤트 구독)
    └── probe ──TCP connect()──► target:5000
          └────────이벤트 발행──► Redis
```

`probe`는 `target:5000`에 TCP 연결을 반복 시도해 상태 이벤트를 Redis에 발행한다. `web_a`와 `web_b`는 각각 별도 WebSocket 서버이며 같은 Redis 채널을 구독한다. Caddy는 **새 연결**을 두 서버에 분배한다. WebSocket 연결은 수립된 뒤 한 서버에 유지되므로 분배 단위는 메시지가 아닌 연결이다. Redis Pub/Sub은 접속 중인 구독자에게 전달하며, 연결이 끊긴 동안의 메시지를 재생하지 않는다. [Redis Pub/Sub 전달 특성](https://redis.io/docs/latest/develop/pubsub/)

`compose.yaml`에서 `web_a`와 `web_b`의 호스트 포트 `8001`·`8002`는 `127.0.0.1`에만 바인딩한다. EC2 외부에서는 이 포트로 직접 접속하지 않는다. Redis `6379`는 호스트에 **게시하지 않는다**. 같은 Compose 네트워크의 컨테이너는 서비스 이름(`web_a`, `web_b`, `redis`)으로 통신한다. [Docker Compose 네트워킹](https://docs.docker.com/compose/how-tos/networking/), [Compose 포트 설정](https://docs.docker.com/reference/compose-file/services/)

## 2. 배포 전 준비

1. 로컬에서 `docker compose up -d --build`와 브라우저 실습을 끝낸다. 두 웹 서버에서 같은 TCP 상태 이벤트를 받을 수 있고 `/health`가 정상 응답하는지 확인한다.
2. AWS 계정의 **해당 리전 요금과 Free Tier 적용 여부를 직접 확인**한다. EC2 인스턴스, EBS 볼륨, 공인 IPv4 주소, 인터넷 송신 트래픽 등에 비용이 발생할 수 있다. [EC2 요금](https://aws.amazon.com/ec2/pricing/on-demand/), [공인 IPv4 요금](https://aws.amazon.com/vpc/pricing/)
3. [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)에서 지출 알림을 설정한다. 알림은 비용 확인 수단이며 리소스를 자동 종료한다고 가정하지 않는다.
4. 소유한 도메인 또는 사용할 수 있는 하위 도메인을 준비한다. DNS A 레코드가 서버를 가리키고, 인증기관에서 TCP 80에 접근할 수 있어야 한다. 이 저장소의 Caddyfile은 **HTTP-01 검증**을 사용하도록 TLS-ALPN-01 검증을 비활성화한다. 따라서 인증기관을 위해 443을 전체 공개할 필요는 없으며, 443은 본인의 브라우저 접속용으로 제한한다. [Caddy의 ACME 검증 방식](https://caddyserver.com/docs/automatic-https#acme-challenges)
5. 프로젝트 파일을 EC2로 옮길 방법을 정한다. 아래 예시는 **공개 Git 저장소**의 `git clone`을 사용한다. 비공개 저장소라면 토큰을 명령줄이나 README에 기록하지 않는 방식으로 전송한다.

## 3. EC2와 보안 그룹 설정

[AWS EC2 시작 안내](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/tutorial-launch-a-test-ec2-instance.html)를 참고해 지원되는 Ubuntu Server AMI로 인스턴스를 만든다. `web_a`, `web_b`, Redis, Caddy가 함께 실행될 메모리를 확보할 수 있는 인스턴스 유형을 고른다. 작은 유형을 무조건 충분하다고 가정하지 말고 로컬 메모리 사용량과 [AWS Pricing Calculator](https://calculator.aws/) 견적을 확인한다.

- VPC의 **퍼블릭 서브넷**에 배치하고, 서브넷 경로 테이블에 Internet Gateway로 향하는 `0.0.0.0/0` 경로가 있는지 확인한다. 인스턴스에 공인 IPv4 주소도 필요하다. 이 둘이 있어야 인터넷에서 인스턴스로 들어올 수 있다. [AWS VPC 인터넷 게이트웨이](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html)
- SSH 키 페어를 안전하게 보관한다. 아래 예시의 Ubuntu 기본 로그인 이름은 `ubuntu`다. 다른 AMI를 선택했다면 로그인 이름을 확인한다.
- EC2 보안 그룹 **인바운드**를 아래처럼 설정한다. 보안 그룹은 허용 규칙만 추가하며 응답 트래픽을 상태 기반으로 처리한다. [AWS 보안 그룹 규칙 예시](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html)

| 목적 | 프로토콜/포트 | 소스 | 이유 |
| --- | --- | --- | --- |
| HTTP 및 인증서 발급 | TCP 80 | `0.0.0.0/0` | Caddy의 공개 인증서 검증과 HTTPS 리다이렉트 |
| HTTPS / WSS | TCP 443 | **본인 공인 IP/32** | 개인 시연용 브라우저 접속 |
| SSH 관리 | TCP 22 | **본인 공인 IP/32** | 관리 접속만 허용 |

표는 개인 시연의 기본값이다. 현재 `/ws` 엔드포인트에는 사용자 인증과 연결 수 제한이 없으므로, 그대로 443을 `0.0.0.0/0`에 개방하면 누구나 접속해 이벤트를 구독하거나 많은 연결을 만들 수 있다. 공개 서비스를 운영하려면 인증, 연결 수 제한 및 사용량 관리를 먼저 구현한다. TCP 80은 최초 발급뿐 아니라 **인증서 갱신 시 HTTP-01 검증에도** 외부에서 접근할 수 있어야 한다. [Caddy의 HTTP-01 요구사항](https://caddyserver.com/docs/automatic-https#http-challenge). 내부 실습용 `5000`, Redis `6379`, 웹 서버 `8001`·`8002` 인바운드 규칙은 **추가하지 않는다**. 도메인 없이 개인적으로 기능만 확인할 때는 로컬 Docker 실습을 사용한다.

## 4. 도메인 연결과 Docker 설치

DNS 관리 화면에서 예를 들어 `lab.example.com`의 **A 레코드**를 EC2의 공인 IPv4로 지정한다. 일반 공인 IPv4는 인스턴스를 중지하고 다시 시작하면 바뀔 수 있다. 주소를 고정해야 한다면 Elastic IP를 검토하되, 유지 비용을 확인한다. DNS 변경 후 도메인이 올바른 주소를 가리키는지 확인한다.

Windows PowerShell에서 EC2에 SSH로 접속하는 예시는 다음과 같다. `<...>` 부분은 실제 값으로 바꾼다.

```powershell
ssh -i "<키파일.pem>" ubuntu@<EC2_공인_IP>
```

EC2의 Ubuntu 셸에서 [Docker 공식 Ubuntu 설치 절차](https://docs.docker.com/engine/install/ubuntu/)에 따라 Docker Engine과 **Docker Compose 플러그인**을 설치한다. 편의 설치 스크립트 대신 공식 `apt` 저장소 절차를 따른다. 설치 확인:

```bash
sudo docker version
sudo docker compose version
```

아래는 저장소를 가져오고 배포하는 **예시**다. GitHub에 프로젝트가 올라온 후 `<OWNER>`와 `<REPO>`를 실제 이름으로 바꾼다. `.env`는 Compose가 읽는 로컬 설정 파일이며 Git에 올리지 않는다.

```bash
git clone https://github.com/<OWNER>/<REPO>.git
cd <REPO>
printf 'DOMAIN=lab.example.com\n' > .env
sudo docker compose --profile aws config
sudo docker compose --profile aws up -d --build
```

`DOMAIN`은 Caddyfile의 `{$DOMAIN}`에 전달된다. 값은 DNS A 레코드의 도메인과 정확히 일치해야 한다. `compose.yaml`의 `aws` 프로필은 Caddy를 추가하고, Caddy는 `web_a:8000`·`web_b:8000`으로 프록시한다. Caddyfile의 `tls { issuer acme { disable_tlsalpn_challenge } }`는 포트 443을 사용하는 TLS-ALPN-01 검증을 끄고, 외부에 열린 포트 80의 HTTP-01 검증을 사용하게 한다. Caddy의 `reverse_proxy`는 WebSocket Upgrade를 처리한다. [Caddy TLS 설정](https://caddyserver.com/docs/caddyfile/directives/tls#acme), [Caddy reverse_proxy 문서](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)

## 5. 배포 확인

EC2의 Ubuntu 셸에서 실행한다.

```bash
sudo docker compose --profile aws ps
sudo docker compose --profile aws logs --tail=100 caddy web_a web_b redis probe target
sudo docker compose --profile aws exec redis redis-cli ping
curl -i http://127.0.0.1:8001/health
curl -i http://127.0.0.1:8002/health
```

예상 상태는 여섯 서비스가 실행 중이고, Redis 명령이 `PONG`을 반환하며, 두 `/health` 요청이 정상 상태를 반환하는 것이다. `/health`는 Redis 연결도 확인하므로 실패하면 앱 로그와 Redis 상태를 함께 본다. `probe` 로그에는 TCP 검사 결과와 Redis 구독자 수가 출력된다. `docker compose ps`에서 `8001`·`8002`가 `127.0.0.1`에만 바인딩되고 Redis에 호스트 포트 매핑이 없는지도 확인한다.

Windows에서는 브라우저로 `https://lab.example.com`에 접속해 두 창에서 TCP 상태 이벤트를 확인한다. 같은 URL을 사용하더라도 새 WebSocket 연결은 `web_a`나 `web_b`로 분배될 수 있다. 연결 시각의 `web_a`·`web_b` 로그에서 어느 서버가 WebSocket 연결을 수락했는지 확인한다. 양쪽 서버에 붙은 브라우저가 같은 probe 이벤트를 받으면 Redis Pub/Sub 경로까지 검증된 것이다. 네트워크 연결만 먼저 확인하려면 PowerShell에서 다음 명령을 쓸 수 있다.

```powershell
Test-NetConnection lab.example.com -Port 443
Invoke-WebRequest https://lab.example.com/health
```

## 6. 장애를 만났을 때

포트 확인은 **클라이언트 → EC2 → Caddy → 앱 → Redis** 순서로 진행한다. `Test-NetConnection` 성공은 TCP 443에 도달했다는 뜻이며 앱과 Redis가 정상이라는 증거는 아니다.

| 관찰 | 먼저 확인할 곳 | 해석의 범위 |
| --- | --- | --- |
| 도메인이 엉뚱한 IP로 해석됨 | DNS A 레코드와 EC2 공인 IP | DNS 또는 주소 변경 가능성 |
| TCP 443 연결 시간 초과 | 공인 IP, 퍼블릭 서브넷 경로, 보안 그룹 443 | 경로 어딘가에서 응답이 없을 수 있음 |
| TCP 443 연결 거부 | Caddy 실행·리스닝 상태, 호스트 포트 매핑 | 대상까지 도달했으나 리스너가 없을 수 있음 |
| 인증서 발급 실패 | 도메인 값, DNS A 레코드, 외부 TCP 80 접근, Caddy 로그 | HTTP-01 검증 경로 또는 설정 문제 가능성 |
| HTTPS 접속은 되지만 502/503 | `web_a`·`web_b` 상태 및 Caddy 로그 | 프록시에서 앱으로 가는 경로 확인 |
| `/health` 오류 | Redis 상태, 앱 로그, Compose 내부 네트워크 | 앱의 Redis 의존성 확인 |
| WebSocket 연결은 되지만 TCP 상태 이벤트가 보이지 않음 | `probe`·두 앱 로그, Redis Pub/Sub 연결 | 이벤트 생성·발행·구독 경로 확인 |

AWS 보안 그룹에서 포트를 막으면 외부 클라이언트에서는 응답 없는 SYN과 시간 초과가 관찰될 수 있다. 반면 Caddy까지 연결된 뒤 앱 컨테이너가 중지된 경우에는 프록시 계층의 오류가 나타날 수 있다. 같은 “접속 실패”라도 **어느 계층까지 도달했는지** 나누어 판단한다. 보안 그룹과 네트워크 ACL의 동작도 다르다. 보안 그룹은 상태 기반이고 네트워크 ACL은 상태 비저장이다. [AWS 보안 그룹 연결 추적](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-connection-tracking.html)

## 7. Wireshark와 WSS 관찰 범위

로컬 `ws://` 실습에서는 HTTP Upgrade 요청, `101 Switching Protocols` 응답, WebSocket 프레임을 패킷에서 비교적 쉽게 확인할 수 있다. AWS의 `wss://`는 TLS로 암호화되므로 일반 Wireshark 캡처에서는 **TCP 연결과 TLS 교환**을 볼 수 있어도 Upgrade 헤더나 메시지 본문을 평문으로 볼 수 없다. 브라우저 개발자 도구의 Network → WS와 앱 로그로 응용 계층을 확인한다. 패킷에 표시되지 않는 내용을 “Wireshark에서 확인했다”고 기록하지 않는다.

## 8. 실습 종료와 비용 정리

컨테이너만 멈추려면 EC2의 프로젝트 폴더에서 다음을 실행한다.

```bash
sudo docker compose --profile aws down
```

이 명령만으로 **EC2 인스턴스 요금이 멈추지 않는다.** 실습을 마쳤다면 AWS 콘솔에서 인스턴스와 필요 없어진 리소스를 정리한다. 다시 사용할 계획이라면 인스턴스를 중지할 수 있지만, **중지 중에도 EBS 저장 비용 등이 남을 수 있다**. 완전히 끝낸 경우 인스턴스를 종료하고, 남은 EBS 볼륨·Elastic IP·불필요한 DNS A 레코드를 확인한다. [EC2 중지·시작 비용](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html)

GitHub README에는 실제로 사용한 AWS 리전, 인스턴스 유형, 보안 그룹 규칙, 도메인(공개해도 되는 경우), 성공·장애 실험의 관찰 결과를 작성한다. 배포하지 않았다면 이 문서를 **배포 계획 및 재현 절차**로 설명한다.
