def add(x, y):
    return x + y

def subtract(x, y):
    return x - y

def multiply(x, y):
    return x * y

def divide(x, y):
    if y == 0:
        return "Error: Division by zero"
    return x / y

def main():
    while True:
        print("\n==== 사칙연산 계산기 ====")
        print("1. 덧셈")
        print("2. 뺄셈")
        print("3. 곱셈")
        print("4. 나눗셈")
        print("5. 나머지")
        print("6. 종료")
        
        choice = input("원하는 연산을 선택하세요 (1-6): ")
        
        if choice == '6':
            print("계산기를 종료합니다.")
            break
        
        if choice not in ['1', '2', '3', '4', '5']:
            print("잘못된 선택입니다. 다시 선택해주세요.")
            continue
        
        try:
            num1 = float(input("첫 번째 숫자를 입력하세요: "))
            num2 = float(input("두 번째 숫자를 입력하세요: "))
        except ValueError:
            print("유효한 숫자를 입력해주세요.")
            continue
        
        if choice == '1':
            result = add(num1, num2)
            print(f"{num1} + {num2} = {result}")
        elif choice == '2':
            result = subtract(num1, num2)
            print(f"{num1} - {num2} = {result}")
        elif choice == '3':
            result = multiply(num1, num2)
            print(f"{num1} * {num2} = {result}")
        elif choice == '4':
            result = divide(num1, num2)
            print(f"{num1} / {num2} = {result}")
        elif choice == '5':
            result = divide(num1, num2)
            print(f"{num1} % {num2} = {result}")

if __name__ == "__main__":
    main()