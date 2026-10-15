# Wireshark·대시보드·로그 증거 수집 가이드

이 문서는 구현과 동작 검증을 마친 뒤, Windows 10/11 + Docker Desktop에서 **실제로 관찰한 화면만** 포트폴리오 증거로 모으는 순서입니다. 실습 명령과 상태의 의미는 [README의 Scenario A–E](../README.md)를 먼저 확인하세요. 아래 파일명은 저장할 스크린샷 이름이며, 아직 촬영하지 않은 화면을 이미 관찰한 것으로 쓰지 않습니다.

## 1. 어느 구간을 캡처하는가

| 통신 구간 | Windows에서 확인할 근거 |
| --- | --- |
| 브라우저 ↔ `localhost:8001/8002` | Wireshark의 Npcap Loopback Adapter(또는 loopback traffic capture 어댑터)에서 TCP 연결, `/ws` HTTP Upgrade, WebSocket 프레임을 찾습니다. Docker Desktop 설정에 따라 보이는 인터페이스가 다를 수 있습니다. |
| `probe` ↔ `target:5000/5001` | Compose 내부 통신입니다. Windows Loopback 화면에 SYN·RST가 반드시 나타나지 않습니다. 일회성 `probe` 출력, 정기 `probe`·`target` 로그와 대시보드 결과를 대조합니다. |
| `probe`/웹 서버 ↔ Redis `:6379` | 역시 Compose 내부 통신입니다. Redis 중지·복구는 `docker compose ps --all`, 두 `/health` 응답, 발행·전달 로그와 화면 배너로 확인합니다. |

Wi-Fi 패킷이 많으면 Wi-Fi가 아니라 **Loopback 캡처 인터페이스**를 먼저 선택하세요. 브라우저 두 주소의 Wireshark 표시 필터는 다음과 같습니다.

```text
tcp.port == 8001 || tcp.port == 8002
```

필터를 입력하기 전 캡처를 시작하고, 브라우저에서 `http://localhost:8001/`과 `http://localhost:8002/`를 새로고침합니다. 캡처한 인터페이스에 패킷이 없으면 필터를 잠시 지워 트래픽 유무를 확인한 뒤, Loopback/가상 인터페이스를 다시 고르세요. 호스트에 공개된 포트는 `8001/8002`이고, 각 웹 컨테이너 안의 포트는 `8000`입니다.

## 2. 시각과 이벤트를 맞추는 법

`probe.py`의 JSON `timestamp`는 **UTC ISO 형식**입니다. 예를 들어 `2026-10-15T13:44:33+00:00`은 한국 표준시(KST) `2026-10-15 22:44:33`입니다. 대시보드는 브라우저의 로컬 시각으로 표시하므로 Windows 시간대가 한국이면 9시간 차이가 납니다. Wireshark의 **Time 열은 패킷을 캡처한 시각**이며 표시 형식에 따라 상대 초 또는 절대 시각으로 보일 수 있습니다. 비교 전 `View → Time Display Format → Date and Time of Day`를 선택하고 Windows 시간대가 올바른지 확인하세요. Wireshark는 절대 시각을 표시할 때 실행 컴퓨터의 로컬 시간대를 사용합니다. [Wireshark 시간 표시](https://www.wireshark.org/docs/wsug_html_chunked/ChWorkTimeFormatsSection.html), [시간대 설명](https://www.wireshark.org/docs/wsug_html_chunked/ChAdvTimezones.html)

하나의 이벤트를 찾을 때는 시각만 보지 말고 `target`, `status`, `timestamp`를 묶어 비교합니다. 정기 검사가 계속 일어나고 표시 시각은 초 단위이므로 근접한 패킷이 여러 개일 수 있습니다. 화면의 `target:5001 · 연결 거부`는 JSON의 `"target":"target:5001"`, `"status":"refused"`와 대응합니다. Wireshark의 WebSocket 메시지에 그 JSON이 실제로 보이면 같은 이벤트인지 대조하고, 그렇지 않으면 브라우저 개발자 도구의 **Network → Socket(또는 WS) → /ws → Messages/Frames**와 `[WEB web_a]`·`[WEB web_b] Event forwarded` 로그를 근거로 사용하세요. 패킷 캡처 시각과 이벤트 생성 시각은 전달 지연 때문에 밀리초까지 같을 필요가 없습니다.

## 3. 한 번에 수집하는 순서

이미 저장된 화면을 위해 실습을 다시 반복할 필요는 없습니다. 아래 순서는 추가 근거를 촬영하거나 전체 실습을 재현할 때 사용합니다.

1. 프로젝트 폴더의 PowerShell에서 `docker compose up --build -d`와 `docker compose ps`를 실행합니다. `curl.exe -i http://localhost:8001/health` 및 `:8002/health`가 HTTP 200인지 확인합니다.
2. 별도 터미널에서 `docker compose logs -f --timestamps --tail=20 probe target web_a web_b`를 열어 둡니다. Wireshark의 Loopback 캡처를 시작하고 위의 `tcp.port` 필터를 적용합니다.
3. 8001과 8002 대시보드를 나란히 열고 새로고침합니다. `GET /`와 `GET /health`에 대한 HTTP `200`은 일반 페이지·상태 확인 응답입니다. WebSocket 연결 증거는 별도의 `GET /ws` 요청과 `101 Switching Protocols` 응답입니다. 전체 `tcp.port` 필터에서 찾기 어렵다면 먼저 8001만 아래 표시 필터로 좁히세요. 캡처를 시작한 **뒤에** 브라우저에서 `Ctrl+F5`를 눌러 새 WebSocket 연결을 만듭니다.

   ```text
   tcp.port == 8001 && (http.request.uri == "/ws" || http.response.code == 101)
   ```

   결과가 없으면 필터를 다시 `tcp.port == 8001`로 넓혀 아래쪽 패킷까지 확인합니다. 포트 때문에 HTTP로 인식하지 못하면 **Analyze → Decode As...**에서 해당 TCP 포트를 HTTP로 지정해 봅니다. 한 연결을 좁힐 때는 해당 패킷의 `tcp.stream` 번호로 `tcp.stream == 번호`를 적용합니다. [Wireshark HTTP 필터 필드](https://www.wireshark.org/docs/dfref/h/http.html), [Decode As 설명](https://www.wireshark.org/docs/wsug_html_chunked/ChCustProtocolDissectionSection.html)
4. 가능하면 그 스트림의 WebSocket 프레임에서 서버가 보낸 JSON을 찾고, 두 대시보드의 대상·상태·시각 및 `probe` 발행 로그, `web_a`·`web_b` 전달 로그와 대조합니다. Wireshark에서 본문을 해석하지 못했다면 브라우저 개발자 도구의 Socket/WS 메시지 화면을 캡처하고, Wireshark 캡처는 TCP/Upgrade 증거로만 설명합니다.
5. 기본 `target:5000`의 `open`을 기록한 뒤, [Scenario B](../README.md#8-scenario-b--connection-refused)의 `target:5001` 일회성 검사를 실행해 `refused`를 기록합니다. `docker compose run --rm ... --once`의 **일회성 출력은 그 PowerShell 터미널에서 보관**하세요. 제거된 일회성 컨테이너의 출력은 정기 서비스용 `docker compose logs probe`에 남는다고 가정하지 않습니다.
6. 두 브라우저를 새로고침해 5번의 일회성 검사 기록을 초기화한 뒤 [Scenario E](../README.md#11-scenario-e--대상별-상태-변화와-연속-실패)의 5001 거부 3회 → 임시 리스너 실행 후 성공 → 리스너 종료 후 거부를 진행합니다. 대상별 상태 표에서 **`target:5001` 행**의 연속 실패와 상태 변화를 확인합니다. `target:5000`의 정기 `open`이 최근 결과 사이에 끼어도 다른 대상으로 집계됩니다.
7. [Scenario D](../README.md#10-scenario-d--redis-장애와-복구)의 Redis 중지·재시작을 같은 두 브라우저 탭에서 수행합니다. 붉은 장애 배너, `/health` 503, `Redis publish failed`를 함께 기록합니다. 재시작 후 `/health` 200과 **새 이벤트** 수신 및 녹색 복구 배너를 확인합니다. Redis 중단 중 전달되지 않은 이벤트를 복구 후 수신했다고 적지 않습니다.
8. [Scenario C](../README.md#9-scenario-c--connection-timeout)의 시간 초과는 **실제로 재현된 경우에만** 추가합니다. 다른 상태가 나왔거나 SYN이 캡처되지 않았다면 그 관찰을 그대로 기록합니다. 캡처를 저장하고 로그 보기를 `Ctrl+C`로 마친 뒤, 실습이 끝났으면 `docker compose down`으로 정리합니다.

## 4. 스크린샷 체크리스트

현재 `images/`에 저장된 아래 10장으로 정상 연결, 연결 거부와 복구, 두 대시보드 수신, Redis 장애와 복구, WebSocket 연결 업그레이드와 수신 메시지를 설명할 수 있습니다. 정상 연결과 거부 결과를 위해 별도 사진을 다시 찍을 필요는 없습니다. 정상 결과는 `대시보드_8001_8002.png`에, 거부 결과는 `대상5001_연속실패.png`와 `대상5001_재거부.png`에 이미 보입니다.

| 이미 저장된 파일 | 실제 화면에서 확인되는 내용 |
| --- | --- |
| `images/대시보드_8001_8002.png` | 8001·8002에서 같은 `target:5000` 연결 성공 결과·관찰 시각·검사 소요 시간. 누적 건수는 브라우저별 수신 기간이 달라 다릅니다. |
| `images/웹소켓_연결전환.png` | `tcp.port == 8001`을 포함한 표시 필터, `GET /ws`, HTTP `101` 두 행. HTTP 헤더 상세와 WebSocket 이벤트 본문은 나오지 않습니다. |
| `images/웹소켓_요청응답_헤더.png` | **Chrome 개발자 도구**의 `ws://localhost:8001/ws`, HTTP `101`, 요청·응답의 Upgrade 헤더. 메시지 본문은 나오지 않습니다. |
| `images/웹소켓_수신메시지.png` | **Chrome 개발자 도구 Messages**의 수신 JSON: `target:5000`, `status:open`, UTC `timestamp`, `latency_ms`. Wireshark 프레임 캡처로 소개하지 않습니다. |
| `images/대상5001_연속실패.png` | `target:5001` 연결 거부 3회 경고와 별도 `target:5000` 행. |
| `images/대상5001_임시서버.png` | 임시 리스너의 `Listening` 및 `Accepted` 기록. 명령 첫 줄은 잘려 있습니다. |
| `images/대상5001_연결복구.png` | `target:5001`이 연결 성공으로 바뀌고 연속 실패 0회로 초기화된 화면. |
| `images/대상5001_재거부.png` | 리스너 종료 후 `target:5001`이 다시 연결 거부, 연속 실패 1회로 표시된 화면. |
| `images/레디스_장애.png` | Redis 중지 후 붉은 장애 배너와 「현재 상태 아님」 표시. 이 화면만으로 TCP 대상 장애를 뜻하지 않습니다. |
| `images/레디스_복구.png` | Redis 재시작 후 녹색 복구 배너와 새 이벤트. 사진 속 `target:5001 refused`는 의도적인 별도 검사 결과입니다. |

현재 진행한 실습을 설명하기 위해 추가 촬영이 반드시 필요하지는 않습니다. Wireshark는 `/ws`·`101` 패킷을 보여주고, 개발자 도구는 요청·응답 헤더와 실제 JSON 메시지를 보여줍니다. 두 화면의 출처를 구분해 적습니다. 필요하다면 Wireshark의 WebSocket 프레임이나 `web_a`·`web_b` 전달 로그를 추가로 대조할 수 있습니다.

Redis 화면의 원인 분석을 더 강하게 보여주고 싶다면 `docker compose ps --all`의 Redis 중지 상태, `/health` HTTP 503, `probe` 발행 오류, `target`의 수락 기록을 터미널에서 추가 촬영할 수 있습니다. 이는 현재 붉은 배너만으로 보이지 않는 전달 경로의 근거입니다. 시간 초과 화면은 실제 시간 초과가 재현됐을 때만 선택적으로 추가하고, 다른 오류나 캡처하지 못한 SYN/재전송을 시간 초과 증거로 쓰지 않습니다.

## 5. GitHub에 올리기 전

- README에 연결된 두 대시보드, 대상별 상태 변화, Redis 장애·복구, WebSocket 업그레이드·개발자 도구 메시지 사진이 실제로 존재하는지, 설명에 적은 대상·포트·상태·시각이 화면과 일치하는지 확인합니다. 아직 촬영하지 않은 선택 사진은 링크하지 않습니다.
- `.env`, 암호·토큰, 불필요한 개인 IP나 계정 정보가 포함되지 않았는지 확인합니다. 필요한 증거인 주소·포트·시각은 지우지 않고 맥락을 설명합니다.
- Wireshark에서 본 구간을 **브라우저↔웹 서버**로, `probe`·Redis 구간은 로그로 확인한 것으로 구분합니다. 원본에 없는 패킷이나 재현되지 않은 시간 초과를 만들지 않습니다.
- `docker compose config`, `python -m py_compile app.py probe.py demo_target.py`, 정상·거부·Redis 복구 시나리오를 마지막으로 확인하고, 프로젝트 폴더를 저장소 루트로 올립니다. AWS를 직접 배포하지 않았다면 EC2 문서는 배포 가이드로 소개합니다.
