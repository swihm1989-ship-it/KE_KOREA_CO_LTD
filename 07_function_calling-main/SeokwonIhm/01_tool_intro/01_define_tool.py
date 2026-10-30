
from langchain_core.tools import tool

AVAILABLITY = {
    "2026-11-25" : { "A" : ["09:00~12:00"], "B" : ["10:00~11:00"]},
    "2026-11-26" : { "A" : ["09:00~12:00"], "B" : ["09:00~12:00"]},
    "2026-11-27" : { "A" : ["09:00~10:00"], "B" : ["11:00~12:00"]},
}

@tool
def read_availiablity(participant_id: str, date: str) -> dict:
    """참가자의 지정한 날짜에 가능한 시간을 조회한다. 날짜는 YYYY-MM-DD이다."""
    return {
        "participant_id" : participant_id,
        "date" : date,
        "times" : AVAILABLITY.get(date, {}).get(participant_id)
    }

print("도구 이름:", read_availiablity.name)
print("도구 설명:", read_availiablity.description)
print("입력 구조:", read_availiablity.args)

arguments = {"participant_id" : "A", "date" : "2026-11-25"}
arguments = {"participant_id" : "B", "date" : "2026-11-25"}
arguments = {"participant_id" : "B", "date" : "2026-11-30"}
result = read_availiablity.invoke(arguments)
print("전달 인자:", arguments)
print("실제 조회 결과:", result)
