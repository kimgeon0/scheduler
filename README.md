# 스케줄러 앱

PySide6 기반의 데스크톱 스케줄러 애플리케이션입니다. 세로 시간표 UI에서 일정을 추가, 편집, 이동, 리사이즈할 수 있고, 스케줄 시작 시각에 실행 파일과 음악 파일을 동작시킬 수 있습니다. 현재 코드베이스는 Windows와 Linux 배포를 염두에 두고 있으며, QtMultimedia를 사용한 음악 재생 팝업을 포함합니다. 기능 구성은 업로드된 현재 코드 기준입니다. fileciteturn13file2turn13file4

---

## 주요 기능

- 현재 시각 중심의 세로 시간표 표시
- 전체 보기 / 현재 기준 보기 전환
- 마우스 휠로 표시 범위 조절
- 드래그 기반 시간표 이동 및 관성 스크롤
- 스케줄 추가 / 편집 / 삭제 / 복제 / 테스트
- 스케줄 이동 및 상하단 리사이즈
- 자정을 넘기는 스케줄 지원
- JSON 불러오기 / 내보내기
- 설정 창에서 테마 색상, 폰트 스타일, 폰트 크기 변경
- 음악 파일 선택, 스케줄별 음악 볼륨 저장, 테스트 재생 팝업
- 스케줄 시작 시 실행 파일 실행 및 음악 재생

---

## 기술 스택

- Python 3.10+
- PySide6
- QtMultimedia (`QMediaPlayer`, `QAudioOutput`)
- JSON 기반 로컬 데이터 저장

---

## 프로젝트 구조 예시

```text
.
├─ scheduler_app.py
├─ schedules.json
├─ settings.json
├─ build_windows.bat
├─ build_linux.sh
├─ scheduler_app.spec
└─ README.md
```

현재 대화에서 작업된 파일명은 여러 버전(`scheduler_app_v12_1.py`, `scheduler_app_v17_theme_font_buttons.py` 등)으로 존재합니다. 배포 전에는 **실제 배포 대상 파일명을 하나로 고정**하는 것을 권장합니다. 예: `scheduler_app.py`. fileciteturn13file1turn13file2

---

## 개발 환경 실행

### 1) 가상환경 생성

#### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install PySide6
```

#### Windows

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install PySide6
```

### 2) 앱 실행

```bash
python scheduler_app.py
```

> 파일명이 다르면 실제 파일명으로 바꾸십시오.

---

## 데이터 파일

앱은 기본적으로 다음 JSON 파일을 사용합니다.

- `schedules.json`: 스케줄 목록
- `settings.json`: 테마 / 폰트 / 기타 설정

현재 코드에서는 이 파일들을 스크립트 디렉터리 기준으로 읽고 쓰도록 구성되어 있습니다. 설치형 배포를 목표로 한다면, 추후 사용자 데이터 디렉터리로 이동하는 방식으로 바꾸는 것을 권장합니다. fileciteturn13file2turn13file4

---

## 스케줄 데이터 예시

```json
[
  {
    "제목": "아침 음악",
    "시작 시각": "08:00",
    "종료 시각": "08:30",
    "표시 색상": "#8fb3ff",
    "실행 파일": null,
    "음악 파일": "/home/user/Music/alarm.mp3",
    "음악 볼륨": 70,
    "메모": "기상용 재생"
  }
]
```

---

## 플랫폼별 실행 파일 동작

현재 코드의 실행 파일 처리 방식은 OS별 차이를 고려해야 합니다.

### 공통
- `.py` 파일: 현재 Python 인터프리터로 실행

### Linux 친화적 동작
- `.sh` 파일: `bash`로 실행
- 실행 권한이 있는 파일: 직접 실행
- 그 외 파일: 기본 앱으로 열기 (`xdg-open` 방식 계열)

### Windows 배포 시 권장 보완
배포 전에 아래 분기 처리를 추가하는 것을 권장합니다.

- `.bat`, `.cmd`, `.ps1`: Windows 명령 처리
- `.exe`: 직접 실행
- 일반 파일: `os.startfile()` 기반 열기

즉, **GUI 자체는 Windows/Linux 모두 가능하지만**, 실행 파일 동작은 플랫폼별 분기 로직을 정리한 뒤 배포하는 것이 가장 안전합니다. 현재 코드에는 Linux 쪽에 더 친화적인 분기가 포함되어 있습니다. fileciteturn13file1turn13file2

---

## 음악 재생 관련

음악 테스트 및 실제 스케줄 재생은 QtMultimedia 기반으로 동작합니다.

- `QMediaPlayer`
- `QAudioOutput`
- 재생 팝업에서 중지 가능
- 테스트 중 볼륨 슬라이더로 실시간 음량 조절 가능

배포 후에는 운영체제와 시스템 코덱 상태에 따라 일부 파일 형식의 재생 가능 여부가 달라질 수 있습니다. MP3, WAV로 우선 테스트하는 것을 권장합니다. 현재 코드에 QtMultimedia 사용이 직접 포함되어 있습니다. fileciteturn13file2turn13file4

---

## 배포 방식

가장 단순하고 현실적인 방법은 **PyInstaller**를 사용하는 것입니다.

### 핵심 원칙
- Windows용 빌드는 **Windows에서**
- Linux용 빌드는 **Linux에서**
- 각 OS에서 별도로 빌드

---

## PyInstaller 설치

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install PySide6 pyinstaller
```

### Windows

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install PySide6 pyinstaller
```

---

## 가장 간단한 빌드

```bash
pyinstaller --noconfirm --windowed --name SchedulerApp scheduler_app.py
```

생성 결과:

- `dist/SchedulerApp/`
- `build/`
- `SchedulerApp.spec`

처음에는 **단일 파일(one-file)** 보다 **폴더형(one-folder)** 배포를 권장합니다. QtMultimedia와 플러그인 문제를 디버깅하기 쉽기 때문입니다.

---

## 권장 spec 파일 예시

`scheduler_app.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("PySide6.QtMultimedia")

a = Analysis(
    ["scheduler_app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SchedulerApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SchedulerApp",
)
```

---

## 빌드 스크립트 예시

### Linux: `build_linux.sh`

```bash
#!/usr/bin/env bash
set -e

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install PySide6 pyinstaller

pyinstaller --noconfirm scheduler_app.spec

echo "완료: dist/SchedulerApp"
```

### Windows: `build_windows.bat`

```bat
@echo off
py -3 -m venv .venv
call .venv\Scripts\activate

python -m pip install --upgrade pip
pip install PySide6 pyinstaller

pyinstaller --noconfirm scheduler_app.spec

echo 완료: dist\SchedulerApp
pause
```

---

## 배포 전 체크리스트

### 공통
- [ ] 앱 정상 실행
- [ ] 설정 창 열림
- [ ] 시간표 렌더링 정상
- [ ] 스케줄 추가/편집/삭제 정상
- [ ] JSON 불러오기/내보내기 정상
- [ ] 자정 넘김 스케줄 정상

### 음악 기능
- [ ] 테스트 재생 가능
- [ ] 중지 버튼 동작
- [ ] 볼륨 슬라이더 실시간 반영
- [ ] 스케줄 시작 시 실제 재생 가능

### 실행 파일 기능
- [ ] `.py` 실행 확인
- [ ] Linux에서 `.sh` 실행 확인
- [ ] Windows에서 `.bat/.cmd/.exe` 처리 확인

---

## 권장 배포 순서

1. 배포 대상 파일명을 하나로 정리 (`scheduler_app.py`)
2. 설정 창 등 런타임 버그를 먼저 수정
3. Windows / Linux 각각에서 직접 실행 테스트
4. PyInstaller one-folder 빌드
5. 빌드 결과를 실제 사용자처럼 테스트
6. 필요하면 나중에 설치형 패키지로 확장

---

## 알려진 주의사항

1. **절대경로 문제**
   - 스케줄에 저장된 실행 파일 / 음악 파일 경로는 다른 PC에서 그대로 유효하지 않을 수 있습니다.

2. **JSON 저장 위치**
   - 현재 구조는 스크립트 경로 기준 저장이라 설치형 배포에는 불리할 수 있습니다.
   - 사용자 데이터 폴더로 옮기는 리팩터링을 권장합니다.

3. **플랫폼별 파일 실행 차이**
   - Windows와 Linux는 실행 파일 처리 방식이 다릅니다.
   - 배포 전에 OS 분기 로직을 넣는 것이 좋습니다.

4. **QtMultimedia / 코덱 차이**
   - 운영체제별로 지원되는 오디오 포맷 차이가 있을 수 있습니다.

---

## 문제 해결

### 설정 창이 열리지 않는 경우
- 최근 수정 중 `SettingsDialog` 내부 메서드 누락 같은 런타임 오류가 있었으므로, 터미널에서 실행 후 traceback을 먼저 확인하십시오.

### Linux에서 Qt xcb 에러가 나는 경우
- 시스템 패키지 부족 가능성이 큽니다.
- 예: `libxcb-cursor0` 등 Qt 런타임 의존성 설치 필요

### 음악이 재생되지 않는 경우
- QtMultimedia 백엔드 / 코덱 문제일 수 있습니다.
- 먼저 WAV 또는 MP3 파일로 테스트하십시오.

---

## 라이선스

배포 전 별도의 라이선스 정책을 정해서 추가하십시오.

예:
- MIT License
- Apache-2.0
- 사내용 비공개 배포

---

## 개발 메모

이 프로젝트는 대화 중 점진적으로 기능이 추가된 버전 기반으로 발전했습니다. 현재 업로드된 코드에는 다음이 포함되어 있습니다.

- 테마 및 폰트 설정 UI
- 음악 재생 테스트 팝업
- JSON import/export
- 자정 넘김 스케줄
- 시간표 기반 드래그 편집

관련 코드 스냅샷은 업로드된 파일들에서 확인할 수 있습니다. fileciteturn13file1turn13file2turn13file4
