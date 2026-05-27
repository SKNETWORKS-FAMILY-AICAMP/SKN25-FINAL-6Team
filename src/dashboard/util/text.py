"""User-facing Korean labels for dashboard frontend data."""

from __future__ import annotations

from typing import Any


COLUMN_LABELS: dict[str, str] = {
    "account_id": "계정 번호",
    "account_status": "계정 상태",
    "analysis_count": "분석 건수",
    "analysis_id": "분석 번호",
    "ai_row_interpretation": "AI 행 해석",
    "analyzed_at": "분석 시각",
    "avg_draft_latency_minutes": "초안 작성 평균 시간",
    "avg_final_latency_minutes": "최종 응답 평균 시간",
    "avg_response_latency_minutes": "첫 응답 평균 시간",
    "avg_relevance_score": "근거 관련성 평균",
    "avg_retrieval_rank": "근거 검색 순위 평균",
    "backlog_metrics": "백로그 지표",
    "category": "문의 분류",
    "channel": "채널",
    "checked_at": "점검 시각",
    "coaching_queue": "품질 코칭 큐",
    "coaching_reason": "품질 검토 사유",
    "column": "확인 항목",
    "created_at": "생성 시각",
    "critical_risk_count": "치명 위험 문의",
    "draft_id": "초안 번호",
    "drafts_without_evidence": "근거 없는 초안",
    "email": "이메일",
    "enriched_query": "정제된 문의 내용",
    "error_category": "실패 유형",
    "error_message": "실패 사유",
    "escalation_queue": "에스컬레이션 큐",
    "escalation_reason": "에스컬레이션 사유",
    "evidence_count": "근거 수",
    "evidence_id": "근거 번호",
    "evidence_linked_drafts": "근거 첨부 초안",
    "evidence_text": "근거 내용",
    "failure_distribution": "실패 분포",
    "factuality_score": "사실성 점수",
    "final_response_count": "최종 응답 수",
    "final_response_ticket_count": "최종 응답 완료 문의",
    "game_name": "게임명",
    "hallucination_score": "환각 위험 점수",
    "high_risk_count": "고위험 문의",
    "human_review_backlog_count": "사람 검토 대기",
    "human_review_count": "사람 검토 필요 문의",
    "inquiry_created_at": "접수 시각",
    "insight": "해석",
    "item_name": "아이템명",
    "label": "구분",
    "latest_analysis_id": "최신 분석 번호",
    "latest_draft_id": "최신 초안 번호",
    "latest_response_created_at": "최신 응답 시각",
    "latest_response_id": "최신 응답 번호",
    "message": "전송 내용",
    "metric": "수치",
    "negative_sentiment_count": "부정 반응 문의",
    "nickname": "이용자 닉네임",
    "notification_channel_distribution": "채널별 실패 분포",
    "notification_error_distribution": "실패 유형 분포",
    "notification_id": "알림 번호",
    "old_pending_count": "24시간 이상 대기 문의",
    "pattern_risk_level": "반복 패턴 위험도",
    "payment_id": "결제 번호",
    "pipeline_gaps": "파이프라인 누락",
    "policy_violation_score": "정책 위반 점수",
    "priority_tickets": "우선 처리 문의",
    "progression_level": "성장 단계",
    "quality_watch_rate": "품질 점검 비율",
    "queue_reason": "우선 처리 사유",
    "quantity": "수량",
    "raw_content": "원문 내용",
    "raw_query": "문의 원문",
    "refund_id": "환불 번호",
    "refund_reason": "환불 사유",
    "refund_status": "환불 상태",
    "relevance_score": "관련성 점수",
    "responded_within_24h_rate": "24시간 내 응답 비율",
    "responder_type": "응답 주체",
    "response_id": "응답 번호",
    "retry_count": "재시도 횟수",
    "retrieval_rank": "근거 검색 순위",
    "risk_hotspots": "위험 집중 구간",
    "risk_level": "위험도",
    "risk_summary": "위험 요약",
    "routing_target": "다음 처리",
    "safety_action": "안전 처리 결과",
    "safety_check_count": "안전 점검 수",
    "safety_reason": "안전 처리 사유",
    "sent_at": "전송 시각",
    "sentiment": "이용자 반응",
    "server_region": "서버 권역",
    "severity": "주의 수준",
    "sla_metrics": "응답 SLA",
    "source_id": "원본 번호",
    "source_type": "접수 경로",
    "status": "처리 상태",
    "summary": "요약",
    "ticket_count": "문의 수",
    "ticket_id": "문의 번호",
    "tickets_without_analysis": "분석 없는 문의",
    "tickets_without_draft": "초안 없는 문의",
    "tickets_without_response": "최종 응답 없는 문의",
    "title": "문의 제목",
    "toxicity_score": "독성 점수",
    "topic_keywords": "주요 키워드",
    "transaction_id": "거래 번호",
    "uid": "게임 계정 UID",
    "unanswered_rate": "미응답 비율",
    "urgent_unanswered_count": "긴급 미응답 문의",
    "user_id": "이용자 번호",
    "user_status": "이용자 상태",
    "value": "값",
    "voc_id": "VOC 번호",
    "voc_type": "VOC 유형",
}


VALUE_LABELS: dict[str, str] = {
    "all": "전체",
    "analysis": "분석",
    "analysis_coverage": "분석 완료 비율",
    "auto_reply": "자동 응답",
    "chat": "채팅",
    "closed": "처리 완료",
    "community": "커뮤니티",
    "completed": "완료",
    "critical": "매우 높음",
    "default channel": "기본 채널",
    "discord": "디스코드",
    "draft_coverage": "초안 작성 비율",
    "email": "이메일",
    "error": "오류",
    "evidence": "근거",
    "factuality": "사실성",
    "failed": "실패",
    "fallback_chat_link": "대체 링크 전송",
    "final_response": "최종 응답 완료 비율",
    "hallucination": "환각 위험",
    "high": "높음",
    "high_risk": "고위험",
    "human_review": "사람 검토 필요",
    "in_app": "인앱 문의",
    "info": "안내",
    "ivr": "전화 문의",
    "line": "추이",
    "low": "낮음",
    "low_factuality": "사실성 낮음",
    "manual": "수동 처리",
    "negative": "부정적",
    "negative_sentiment": "부정 반응",
    "needs_human_review": "사람 검토 필요",
    "neutral": "보통",
    "off": "꺼짐",
    "on": "켜짐",
    "open": "진행 중",
    "payment": "결제",
    "pending": "처리 대기",
    "policy_violation": "정책 위반",
    "positive": "긍정적",
    "processing": "처리 중",
    "publish": "전송",
    "quality_review": "품질 재검토",
    "rag_reply": "AI 문서 기반 응답",
    "refund": "환불",
    "response_rate": "응답 완료 비율",
    "retry_detected": "재시도 발생",
    "review": "검토",
    "safe": "문제 없음",
    "slack": "슬랙",
    "sms": "문자",
    "stop": "종료",
    "success": "성공",
    "system": "시스템",
    "ticket": "문의",
    "toxicity": "독성 위험",
    "unknown": "확인 필요",
    "urgent_alert": "즉시 알림",
    "urgent_unanswered": "긴급 미응답",
    "very_negative": "매우 부정적",
    "very_positive": "매우 긍정적",
    "voice": "음성 문의",
    "warning": "주의",
    "web": "웹 문의",
}


SECTION_LABELS: dict[str, str] = {
    "admin_event_logs": "운영 처리 이력",
    "failed_queries": "조회 실패 기록",
    "gacha_logs": "가챠 이용 기록",
    "item_delivery_logs": "아이템 지급 기록",
    "payments": "결제 기록",
    "refunds": "환불 기록",
}


TRANSLATABLE_KEYS = {
    "severity",
    "status",
    "risk_level",
    "pattern_risk_level",
    "sentiment",
    "routing_target",
    "source_type",
    "channel",
    "delivery_mode",
    "responder_type",
    "safety_action",
    "error_category",
    "kind",
    "label",
    "queue_reason",
    "coaching_reason",
    "escalation_reason",
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
    if key in TRANSLATABLE_KEYS and isinstance(value, str):
        parts = [part.strip().lower() for part in value.split(",")]
        translated = [VALUE_LABELS.get(part, part if part else "-") for part in parts]
        return ", ".join(translated)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALUE_LABELS:
            return VALUE_LABELS[normalized]
    return value


def localized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {translate_label(key): translate_value(value, key=key) for key, value in row.items()}
        for row in rows
    ]
