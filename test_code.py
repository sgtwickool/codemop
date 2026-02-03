#!/usr/bin/env python3

# Simple Python code with some intentional issues for AI to find

def calculate_average(numbers):
    """Calculate average of numbers - has a bug!"""
    if len(numbers) == 0:
        return 0  # Bug: Should probably return None or raise exception
    
    total = 0
    for num in numbers:
        total += num
    
    average = total / len(numbers)  # Potential division by zero if not checked properly
    return average

def process_data(data):
    """Process data with some code quality issues"""
    result = []
    
    # Inefficient loop
    for i in range(len(data)):
        item = data[i]
        if item is not None:
            result.append(item.upper())
    
    # No error handling for file operations
    with open("output.txt", "w") as f:
        for item in result:
            f.write(item + "\n")
    
    return result

def main():
    """Main function with unused variables"""
    test_data = [1, 2, 3, 4, 5]
    unused_var = "This variable is never used"
    another_unused = 42
    
    avg = calculate_average(test_data)
    print(f"Average: {avg}")
    
    # No return value used
    process_data(["hello", "world"])

if __name__ == "__main__":
    main()