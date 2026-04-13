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
