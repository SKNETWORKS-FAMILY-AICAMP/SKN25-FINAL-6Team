"""User-facing Korean labels for dashboard frontend data."""

from __future__ import annotations

from typing import Any


COLUMN_LABELS: dict[str, str] = {
    "account_id": "계정 번호",
    "account_status": "계정 상태",
    "analysis_count": "분석 건수",
    "analysis_id": "분석 번호",
    "ai_row_interpretation": "AI 한줄 해석",
    "analyzed_at": "분석 시각",
    "avg_final_latency_minutes": "최종 답변까지 걸린 평균 시간",
    "category": "문의 분류",
    "channel": "보낸 곳",
    "checked_at": "점검 시각",
    "column": "확인 항목",
    "created_at": "생성 시각",
    "draft_id": "초안 번호",
    "email": "이메일",
    "enriched_query": "정리된 문의 내용",
    "error_category": "실패 유형",
    "error_message": "실패 사유",
    "evidence_text": "근거 내용",
    "factuality_score": "사실성 점수",
    "hallucination_score": "사실과 다른 내용 위험",
    "insight": "해석",
    "inquiry_created_at": "접수 시각",
    "item_name": "아이템 이름",
    "kind": "표시 방식",
    "label": "구분",
    "message": "보낸 내용",
    "metric": "수치",
    "nickname": "이용자 닉네임",
    "notification_id": "알림 번호",
    "payment_id": "결제 번호",
    "pattern_risk_level": "반복 패턴 위험도",
    "policy_violation_score": "운영 정책 위반 위험",
    "progression_level": "성장 단계",
    "quantity": "수량",
    "raw_content": "원문 내용",
    "raw_query": "문의 원문",
    "refund_id": "환불 번호",
    "refund_reason": "환불 사유",
    "refund_status": "환불 상태",
    "relevance_score": "관련성 점수",
    "responder_type": "답변 주체",
    "response_id": "답변 번호",
    "retry_count": "재시도 횟수",
    "retrieval_rank": "근거 추천 순서",
    "risk_level": "위험도",
    "routing_target": "응대",
    "safety_action": "안전 처리 결과",
    "safety_reason": "안전 처리 사유",
    "sent_at": "보낸 시각",
    "sentiment": "이용자 반응",
    "server_region": "서버 권역",
    "severity": "주의 수준",
    "source_id": "원본 번호",
    "source_type": "접수 경로",
    "status": "처리 상태",
    "summary": "한줄 정리",
    "ticket_id": "문의 번호",
    "title": "문의 제목",
    "toxicity_score": "공격적 표현 위험",
    "topic_keywords": "주요 키워드",
    "transaction_id": "거래 번호",
    "uid": "게임 계정 식별값",
    "user_id": "이용자 번호",
    "user_status": "이용자 상태",
    "value": "값",
    "voc_id": "의견 번호",
    "voc_type": "의견 종류",
}

VALUE_LABELS: dict[str, str] = {
    "all": "전체",
    "analysis": "분석",
    "analysis_coverage": "분석까지 끝난 비율",
    "auto_reply": "자동 답변",
    "bar": "막대형",
    "chat": "채팅",
    "closed": "처리 완료",
    "community": "커뮤니티",
    "completed": "완료",
    "critical": "매우 높음",
    "default channel": "기본 채널",
    "discord": "디스코드",
    "draft_coverage": "초안까지 만든 비율",
    "email": "이메일",
    "error": "오류",
    "evidence": "붙인 근거 수",
    "factuality": "사실성",
    "failed": "실패",
    "fallback_chat_link": "대화방 링크로 대체",
    "final_response": "최종 답변까지 끝난 비율",
    "high": "높음",
    "hallucination": "사실과 다른 내용 위험",
    "human_review": "사람 확인 필요",
    "in_app": "앱 안 문의",
    "info": "안내",
    "ivr": "전화 문의",
    "line": "추이형",
    "low": "낮음",
    "manual": "수동 처리",
    "negative": "부정적",
    "neutral": "보통",
    "off": "꺼짐",
    "on": "켜짐",
    "open": "진행 중",
    "payment": "결제",
    "pending": "처리 대기",
    "policy_violation": "운영 정책 위반 위험",
    "positive": "긍정적",
    "processing": "처리 중",
    "publish": "전송",
    "refund": "환불",
    "response_rate": "답변까지 끝난 비율",
    "review": "검토",
    "safe": "문제 없음",
    "slack": "슬랙",
    "sms": "문자",
    "stop": "종료",
    "success": "성공",
    "system": "시스템",
    "ticket": "문의",
    "toxicity": "공격적 표현 위험",
    "unknown": "알 수 없음",
    "rag_reply":"AI 기반 문서 검색",
    "urgent_alert": "담당자에게 전달",
    "very_negative": "매우 부정적",
    "very_positive": "매우 긍정적",
    "voice": "음성 문의",
    "warning": "주의",
    "web": "웹 문의",
}

SECTION_LABELS: dict[str, str] = {
    "admin_event_logs": "운영 처리 이력",
    "failed_queries": "조회 실패 기록",
    "gacha_logs": "뽑기 이용 기록",
    "item_delivery_logs": "아이템 지급 기록",
    "payments": "결제 기록",
    "refunds": "환불 기록",
}


def translate_label(label: str) -> str:
    return COLUMN_LABELS.get(label, label)


def translate_value(value: Any, *, key: str | None = None) -> Any:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if key == "column" and isinstance(value, str):
        return translate_label(value)
    if key in {"severity", "status", "risk_level", "pattern_risk_level", "sentiment", "routing_target", "source_type", "channel", "delivery_mode", "responder_type", "safety_action", "error_category", "kind", "label"} and isinstance(value, str):
        normalized = value.strip().lower()
        return VALUE_LABELS.get(normalized, value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALUE_LABELS:
            return VALUE_LABELS[normalized]
    return value


def localized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for row in rows:
        translated.append({translate_label(key): translate_value(value, key=key) for key, value in row.items()})
    return translated
