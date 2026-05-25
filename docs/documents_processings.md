# Documents Processing

## 1. 목적

`documents_processing`은 DB의 `documents` 원문을 읽어서,  
문서 검색에 바로 사용할 수 있는 `documents_chunks`와 `documents_embeddings`를 생성하는 파이프라인입니다.

핵심 목표는 3가지입니다.

- 한국어가 깨지지 않게 텍스트를 안정적으로 정리한다.
- 검색 성능이 잘 나오도록 문서를 적절한 크기의 chunk로 분할한다.
- 각 chunk를 벡터화해서 hybrid retrieval에 바로 연결한다.

---

## 2. 전체 흐름

```text
documents
  -> 텍스트 정규화
  -> 문단/문맥 기준 chunk 분할
  -> chunk별 embedding 생성
  -> documents_chunks 저장
  -> documents_embeddings 저장
```

실제 적재 순서는 아래와 같습니다.

1. `documents.raw_content` 조회
2. 한국어 안전 정규화 수행
3. 검색 친화적 chunk 생성
4. OpenAI embedding 생성
5. `documents_chunks` 저장
6. `documents_embeddings` 저장

---

## 3. 입력 / 출력 테이블

### 입력

- `documents`
  - `documents_id`
  - `source_type`
  - `category`
  - `title`
  - `raw_content`

### 출력

- `documents_chunks`
  - 검색용 문서 조각 저장
  - `chunk_id`, `document_id`, `chunk_text`, `chunk_order`, `token_count`

- `documents_embeddings`
  - chunk별 벡터 저장
  - `embedding_id`, `chunk_id`, `embedding_vector`, `embedding_model`

---

## 4. 한국어 안전 정규화 방식

문서 정규화는 “의미를 지우지 않고 검색 품질만 높이는 것”이 원칙입니다.

### 유지하는 것

- 한글 원문
- 제목 구조
- 문단 구분
- URL
- 숫자, 버전, 코드, 상품명
- 검색에 의미가 있는 특수기호
  - `/`, `:`, `-`, `(`, `)`, `#`, `|`

### 정리하는 것

- BOM
- zero-width 문자
- 제어문자
- 비정상 공백
- 과도한 빈 줄
- 장식용 구분선

### 효과

- 한글 자모 분리/결합 차이 감소
- 특수문자 때문에 키워드가 사라지는 문제 방지
- 검색용 chunk 텍스트 품질 안정화

---

## 5. Chunk 분할 방식

chunk는 “너무 짧지도, 너무 길지도 않게” 만들고,  
검색 시 문맥이 잘 이어지도록 overlap을 둡니다.

### 기본 전략

- 문단 경계를 우선 사용
- 제목이 나오면 새 chunk 시작 후보로 사용
- 너무 긴 문단만 추가 분할
- 짧은 문단은 앞뒤 문단과 병합

### 현재 기준

- 목표 크기: 약 `400 ~ 700 token`
- overlap: 약 `50 ~ 100 token`

### chunk 생성 규칙

- `chunk_id = {document_id}::chunk::{chunk_order}`
- 문서 title을 chunk 앞에 붙여 문맥 유지
- `chunk_order`는 문서 내 순서를 보존
- `token_count`를 함께 저장

### 기대 효과

- 검색 recall 향상
- 문맥이 잘린 채로 검색되는 문제 감소
- 답변 생성 시 근거 문장 연결성이 좋아짐

---

## 6. Embedding 생성 방식

각 chunk는 embedding 모델로 벡터화됩니다.

### 처리 방식

- chunk 1개당 embedding 1개 생성
- `embedding_id = {chunk_id}::embedding`
- 사용 모델명은 `embedding_model` 컬럼에 저장

### 저장 정보

- `chunk_id`
- `embedding_vector`
- `embedding_model`
- `source_type`
- `category`

### 기대 효과

- pgvector cosine similarity 검색 가능
- keyword 검색 + vector 검색을 함께 쓰는 hybrid retrieval 연결 가능

---

## 7. 적재 정책

현재 구현은 **문서 단위 재생성 방식**입니다.

### 동작 방식

특정 `document_id`를 다시 처리할 때:

1. 해당 문서의 기존 `documents_chunks` 삭제
2. 해당 문서의 기존 `documents_embeddings` 삭제
3. 새 chunk / embedding 재생성
4. 새 데이터 저장

### 장점

- 구현이 단순함
- 데이터 불일치 가능성이 낮음
- chunk 순서와 embedding을 항상 동일 기준으로 맞출 수 있음

---

## 8. 코드 구조

`src/common/documents_processing`

- `normalize.py`
  - 한국어 안전 텍스트 정규화
- `chunking.py`
  - 문단 기반 chunk 분할
- `embed.py`
  - chunk embedding 생성
- `repository.py`
  - DB 조회 / 삭제 / 저장
- `pipeline.py`
  - 전체 orchestration
- `cli.py`
  - 실제 배치 실행 진입점

---

## 9. 실행 명령어

### 전체 적재

```powershell
python -m src.common.documents_processing.cli
```

### 실제 저장 없이 dry run

```powershell
python -m src.common.documents_processing.cli --dry-run
```

### 특정 문서만 적재

```powershell
python -m src.common.documents_processing.cli --document-id DOC123
```

### source/category 필터 적재

```powershell
python -m src.common.documents_processing.cli --source-type policy --category payment
```

### 일부만 테스트 적재

```powershell
python -m src.common.documents_processing.cli --limit 100
```

---

## 10. 환경 변수

실행 전 아래 값이 필요합니다.

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `LLM_API_KEY`
- `EMBEDDING_MODEL` (없으면 기본값 사용)

---

## 11. 발표용 핵심 요약

### 한 줄 설명

`documents_processing`은 원문 문서를 검색 가능한 chunk와 vector embedding으로 변환하는 전처리 파이프라인이다.

### 강조 포인트

- 한국어가 깨지지 않도록 Unicode/공백/특수기호를 보존 중심으로 정규화
- 문단과 제목 구조를 살린 chunk 분할
- chunk별 embedding 생성으로 vector 검색 지원
- `documents -> documents_chunks -> documents_embeddings` 구조로 RAG 검색 준비 완료

### 기대 효과

- FAQ / 정책 / 공지 문서를 검색 근거로 재사용 가능
- keyword 검색과 vector 검색을 함께 쓰는 hybrid retrieval 가능
- 운영 답변 생성 시 더 정확한 근거 문서 연결 가능
