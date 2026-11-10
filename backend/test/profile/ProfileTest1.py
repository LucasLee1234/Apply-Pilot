import json
from datetime import datetime, timezone
import uuid

from sqlalchemy.testing import exclude

from common.database import get_db
from modules.profile.models import ApplicantProfile
from modules.profile.schemas import ProfileDraftFields
from modules.profile.service import ApplicantProfileService
from modules.profile.utils import SECTIONS
from modules.profile.validation import FormalProfileInput

session = next(get_db())

applicantService = ApplicantProfileService(session)


def test_get_profile_by_user_id(user_id: uuid.UUID):
    profile = applicantService.obtain_profile_by_user_id(user_id)
    print(profile.user_id)


def intToRoman(num: int) -> str:
    symbols = [
        ("I", 1),
        ("V", 5),
        ("X", 10),
        ("L", 50),
        ("C", 100),
        ("D", 500),
        ("M", 1000)
    ]
    i = len(symbols) - 1
    output = ""
    while i >= 0:
        key, value = symbols[i]
        if num // value == 0:
            i = i - 2
            continue
        if num // value == 9:
            key1, value1 = symbols[i + 2]
            output = output + key + key1
        if num // value == 4:
            key1, value1 = symbols[i + 1]
            output = output + key + key1
        if 1 <= num // value <= 3:
            output = output + key * 3
        if 6 <= num // value <= 8:
            key1, value1 = symbols[i + 1]
            output = output + key1 + key * ((num // value) - 5)
        num = num % value
    return output


def threeSum(nums: list[int]) -> list[list[int]]:
    def pick(first, ns):
        candidates = []
        for i, n in enumerate(ns):
            negative_nums = [-n for n in ns[i + 1:]]
            if first + n in negative_nums:
                candidates.append([first, n, -(first + n)])
        return candidates

    sorted_nums = sorted(nums)
    result = []
    for i, num in enumerate(sorted_nums):
        if num <= 0:
            candidates = pick(num, sorted_nums[i + 1:])
            for candidate in candidates:
                if candidate not in result:
                    result.append(candidate)
    return result


def threeSumClosest(nums: list[int], target: int) -> int:
    if len(nums) == 3:
        return sum(nums)
    sorted_nums = sorted(nums)
    result = sum(nums[0:3])
    dis = abs(sum(nums[0:3]) - target)
    for i in range(len(sorted_nums)):
        first = sorted_nums[i]
        left = i + 1
        right = len(sorted_nums) - 1
        while left < right:
            three_sum = first + sorted_nums[left] + sorted_nums[right]
            if abs(three_sum - target) < dis:
                result = three_sum
                dis = abs(three_sum - target)
            if three_sum < target:
                left += 1
            if three_sum > target:
                right -= 1
            if three_sum == target:
                return result
    return result




if __name__ == "__main__":
    # for section in SECTIONS:
    #     schema, _, _ = SECTIONS[section]
    #     s = schema.model_construct()
    #     print(s.model_dump(exclude_unset=True))
    # format_changes = {"profile": {"data": ProfileDraftFields()}}
    # format_changes["profile"]["data"].first_name = "a"
    # format_changes["profile"]["id"] = "123e"
    # print(format_changes)
    # print("skills[f697e2be-2631-497d-a00c-1f4314cf529b]".split("[")[1].split("]")[0])
    # format_changes = {"profile": {}}
    # print(format_changes.get("profile"))
    # print(intToRoman(324))
    # threeSum([-1,0,1,2,-1,-4])
    print(threeSumClosest([-1000,-5,-5,-5,-5,-5,-5,-1,-1,-1], -14))