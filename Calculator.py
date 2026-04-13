# Simple Calculator

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        return "Cannot divide by zero"
    return a / b

# Test the calculator
print("Addition: 10 + 5 =", add(10, 5))
print("Subtraction: 10 - 5 =", subtract(10, 5))
print("Multiplication: 10 * 5 =", multiply(10, 5))
print("Division: 10 / 5 =", divide(10, 5))
a = float(input("Enter first number: "))
b = float(input("Enter second number: "))
op = input("Choose (+, -, *, /): ")

if op == "+":
    print(add(a, b))
elif op == "-":
    print(subtract(a, b))
elif op == "*":
    print(multiply(a, b))
elif op == "/":
    print(divide(a, b))
else:
    print("Invalid operator")
while True:
    op = input("Choose (+, -, *, /) or q to quit: ")

    if op.lower() == "q":
        print("Calculator closed.")
        break

    a = float(input("Enter first number: "))
    b = float(input("Enter second number: "))

    if op == "+":
        print("Result:", add(a, b))
    elif op == "-":
        print("Result:", subtract(a, b))
    elif op == "*":
        print("Result:", multiply(a, b))
    elif op == "/":
        print("Result:", divide(a, b))
    else:
        print("Invalid operator")
