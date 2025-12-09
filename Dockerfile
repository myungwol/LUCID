# 1. 가볍고 빠른 파이썬 버전(3.11 slim)을 베이스로 가져옵니다.
FROM python:3.11-slim

# 2. 컨테이너 내부의 작업 폴더를 /app으로 설정합니다.
WORKDIR /app

# 3. [최적화 핵심] 명세서(requirements.txt)만 먼저 복사합니다.
COPY requirements.txt .

# 4. [최적화 핵심] 라이브러리를 설치합니다.
# 코드를 고쳐도 명세서가 안 바뀌면, 이 단계는 건너뛰고 캐시된 걸 씁니다! (속도 엄청 빠름)
RUN pip install --no-cache-dir -r requirements.txt

# 5. 나머지 코드(main.py 등)를 복사합니다.
# 코드 수정 시 여기부터만 다시 실행됩니다.
COPY . .

# 6. 봇을 실행합니다.
CMD ["python", "main.py"]
