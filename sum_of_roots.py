# manba kep.uz


import math
from timer import timer_function
link = "https://kep.uz/practice/problems/problem/5"

# this case we are usig O(N)😭 loops and O(1) memory this is bad but this code for brut force answer 
 
def sum_of_root(number: int)-> int:
    result = 0 

    for i in range(number+1):
        result+= math.sqrt(i)//1
    
    return int(result)

print(sum_of_root(10)), 

print(timer_function("sum_of_root(100000)",1000))




# time O(_/n) and memory is O(1) 


######################################################
# 2 
def sum_of_root(number: int) -> int:
    result = 0
    for i in range(1, int(number**0.5) + 1):
        result += i **2
    return result
print(sum_of_root(4))

print(timer_function("sum_of_root(100000)", 1000))
