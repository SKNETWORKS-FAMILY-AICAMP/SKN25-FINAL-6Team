"""답변 생성 agent 자리 표시자.

Airflow가 매일 04:00(KST)에 이 진입점을 실행한다.
답변해야하는 문의가 뭔지 필터링도 해라. source_type이 naver_cafe인걸로.

apps\cs_auto\backend\agents\analysis_agent.py가 분석해준 내용을 기반으로, 
apps\cs_auto\backend\agents\retrieval.py를 활용해서 답변에 필요한 내용 수집한다.

"""

"""
호출 수 아까우니까 우선 여기서 문의 별로 답변 근거 찾는 함수를 선언한다.
"""

"""
langchain LECL 써서 답변하라.
그럼 여기에 각각의 답변에 대한 문서 및 DB 정보를 retrieval.py 코드 기반으로 가져와 답변을 만드는 함수를 선언한다.
"""

def run_answer_agent() -> None:
    """
    매일 실행되는 답변 생성 작업의 진입점.

    """

    pass

def regenerate_agent() -> None:
    """프론트엔드에서 재생성 버튼 누를 때는, 이게 실행된다.
    위랑 동일한 로직을 쓰는데, 프롬프트에 운영자가 넣은 재생성 사유를 넣을 수 있도록 한다.
    
    """
    pass