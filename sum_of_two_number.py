
## manba kep.uz

link = "https://kep.uz/practice/problems/problem/1"


def add_number(son1 : int, son2 : int) -> int:

    try:
        if son1>=1 and son1<=1000 and son2>=1 and son2<=1000 :

                return son1 +son2
        else:
             
             return "out of range"
    except:
        raise Exception("type error")
    
print(add_number(100,56))
