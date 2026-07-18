"""
External coding grader with hidden test cases.

This grader evaluates candidate solutions against objective test cases
that are NOT shown in the task prompts, ensuring honest evaluation.
"""

import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Tuple


# Hidden test cases for each task (not shown to the model)
HIDDEN_TEST_CASES = {
    "fizzbuzz": [
        (1, "1"),
        (3, "1,2,Fizz"),
        (5, "1,2,Fizz,4,Buzz"),
        (15, "1,2,Fizz,4,Buzz,Fizz,7,8,Fizz,Buzz,11,Fizz,13,14,FizzBuzz"),
        (30, "1,2,Fizz,4,Buzz,Fizz,7,8,Fizz,Buzz,11,Fizz,13,14,FizzBuzz,16,17,Fizz,19,Buzz,Fizz,22,23,Fizz,Buzz,26,Fizz,28,29,FizzBuzz"),
    ],
    "is_palindrome": [
        ("a", True),
        ("racecar", True),
        ("A man a plan a canal Panama", True),
        ("hello", False),
        ("was it a car or a cat i saw", True),
        ("Madam", True),
        ("abcdef", False),
        ("12321", True),
        ("1234", False),
    ],
    "find_prime": [
        (2, True),
        (3, True),
        (4, False),
        (5, True),
        (17, True),
        (20, False),
        (97, True),
        (100, False),
        (1, False),
        (0, False),
    ],
    "reverse_string": [
        ("hello", "olleh"),
        ("a", "a"),
        ("ab", "ba"),
        ("abc", "cba"),
        ("12345", "54321"),
        ("", ""),
    ],
    "remove_duplicates": [
        ([1, 2, 2, 3], [1, 2, 3]),
        ([1], [1]),
        ([], []),
        ([1, 1, 1], [1]),
        ([5, 4, 3, 2, 1], [5, 4, 3, 2, 1]),
        ([1, 2, 1, 3, 2, 4], [1, 2, 3, 4]),
    ],
    "fibonacci_nth": [
        (0, 0),
        (1, 1),
        (2, 1),
        (3, 2),
        (4, 3),
        (5, 5),
        (6, 8),
        (10, 55),
    ],
    "binary_search": [
        ([1, 3, 5, 7], 5, 2),
        ([1, 3, 5, 7], 1, 0),
        ([1, 3, 5, 7], 7, 3),
        ([1, 3, 5, 7], 4, -1),
        ([1], 1, 0),
        ([1], 2, -1),
        ([], 1, -1),
        ([1, 2, 3, 4, 5], 1, 0),
    ],
    "count_vowels": [
        ("hello", 2),
        ("aeiou", 5),
        ("AEIOU", 5),
        ("bcdfg", 0),
        ("", 0),
        ("Hello World", 3),
        ("Python", 1),
    ],
}

TIMEOUT_SECONDS = 5


def grade_solution(task_id: str, solution_file: str) -> Dict:
    """
    Grade a candidate solution against hidden test cases.

    Args:
        task_id: ID of the task (key in HIDDEN_TEST_CASES)
        solution_file: Path to file containing the candidate solution

    Returns:
        Dict with keys:
            - task_id: The task ID
            - passed: Number of test cases passed
            - total: Total number of test cases
            - results: List of per-case results
            - success: True if all tests passed
            - error: Error message if grading failed
    """

    if task_id not in HIDDEN_TEST_CASES:
        return {
            "task_id": task_id,
            "passed": 0,
            "total": 0,
            "results": [],
            "success": False,
            "error": f"Unknown task: {task_id}",
        }

    # Read the solution file
    try:
        with open(solution_file, 'r', encoding='utf-8') as f:
            solution_code = f.read()
    except Exception as e:
        return {
            "task_id": task_id,
            "passed": 0,
            "total": 0,
            "results": [],
            "success": False,
            "error": f"Failed to read solution file: {e}",
        }

    # Get the entrypoint function name from task definition
    try:
        with open(Path(__file__).parent / "coding_tasks.jsonl", 'r') as f:
            for line in f:
                task = json.loads(line)
                if task['id'] == task_id:
                    entrypoint = task['entrypoint']
                    break
            else:
                return {
                    "task_id": task_id,
                    "passed": 0,
                    "total": 0,
                    "results": [],
                    "success": False,
                    "error": f"Task not found in coding_tasks.jsonl: {task_id}",
                }
    except Exception as e:
        return {
            "task_id": task_id,
            "passed": 0,
            "total": 0,
            "results": [],
            "success": False,
            "error": f"Failed to read task definition: {e}",
        }

    # Create a temporary file to execute
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        temp_file = f.name
        f.write(solution_code)

    try:
        test_cases = HIDDEN_TEST_CASES[task_id]
        results = []
        passed_count = 0

        for i, test_case in enumerate(test_cases):
            # Extract input and expected output
            if len(test_case) == 2:
                if isinstance(test_case[0], (list, tuple)) and not isinstance(test_case[0], str):
                    # Multiple arguments
                    args = test_case[0]
                    expected = test_case[1]
                else:
                    # Single argument
                    args = (test_case[0],)
                    expected = test_case[1]
            else:
                args = test_case[:-1]
                expected = test_case[-1]

            # Build the execution command
            args_repr = ", ".join(
                json.dumps(arg) if isinstance(arg, (str, list)) else repr(arg)
                for arg in args
            )

            exec_code = f"""
import sys
sys.path.insert(0, {repr(str(Path(temp_file).parent))})
exec(open({repr(temp_file)}).read())
result = {entrypoint}({args_repr})
print(json.dumps(result))
"""

            try:
                result = subprocess.run(
                    [sys.executable, '-c', f'import json\n{exec_code}'],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS,
                )

                if result.returncode != 0:
                    results.append({
                        "test": i,
                        "input": args,
                        "expected": expected,
                        "passed": False,
                        "error": result.stderr.strip() or "Non-zero return code",
                    })
                else:
                    try:
                        actual = json.loads(result.stdout.strip())
                        passed = actual == expected
                        if passed:
                            passed_count += 1
                        results.append({
                            "test": i,
                            "input": args,
                            "expected": expected,
                            "actual": actual,
                            "passed": passed,
                        })
                    except json.JSONDecodeError:
                        results.append({
                            "test": i,
                            "input": args,
                            "expected": expected,
                            "passed": False,
                            "error": f"Output not JSON: {result.stdout.strip()}",
                        })
            except subprocess.TimeoutExpired:
                results.append({
                    "test": i,
                    "input": args,
                    "expected": expected,
                    "passed": False,
                    "error": f"Timeout after {TIMEOUT_SECONDS}s",
                })
            except Exception as e:
                results.append({
                    "test": i,
                    "input": args,
                    "expected": expected,
                    "passed": False,
                    "error": f"Execution error: {e}",
                })

        return {
            "task_id": task_id,
            "passed": passed_count,
            "total": len(test_cases),
            "results": results,
            "success": passed_count == len(test_cases),
        }

    finally:
        # Clean up temp file
        try:
            os.unlink(temp_file)
        except:
            pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python coding_grader.py <task_id> <solution_file>")
        sys.exit(1)

    task_id = sys.argv[1]
    solution_file = sys.argv[2]

    result = grade_solution(task_id, solution_file)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)
