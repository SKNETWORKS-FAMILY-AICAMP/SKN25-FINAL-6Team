import sys
sys.path.insert(0, "packages/common-python/src")

from dotenv import load_dotenv
load_dotenv(".env", override=True)

from common.documents_processing.pipeline import run_documents_pipeline

for source_type in [
    "hoyoverse_qna_common",
    "hoyoverse_qna_onlygenshin",
    "hoyoverse_policy",
    "naver_cafe_notice",
    "naver_cafe_guide",
]:
    result = run_documents_pipeline(source_type=source_type, dry_run=False, test_mode=True)
    print(source_type)
    print("  문서수:", result.total_documents)
    print("  예상 청크수:", result.total_chunks)
    print()
