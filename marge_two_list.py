from typing import Iterable

def marge_list(arr1 : list[int], arr2 : list[int])->list[int]:

# "  
#     1 ,3, 5, 7 , 15, 16
#     ^ 
#     8 , 10 ,13 
#     ^
# "
##   xotira O(n+m)
##   vaqt esa  O((n+m)log(n+m))


    result = []
    i = 0
    j = 0 
    n , m  = len(arr1), len(arr2)

    while i < n and j< m :
        if arr1[i] < arr2[j]:
            result.append(arr1[i])
            i+= 1
        else:
            result.append(arr2[j])
            j += 1 


    while i < n :
        result.append(arr1[i])
        i += 1

    while j < m :
        result.append(arr2[j])
        j+= 1

    
    return result

arr3 = [1,2,4,6,8]
arr4 = [3,5,7,10,13,14]
print(marge_list(arr3 ,arr4))


## agarda xotiradan qoshimcha result uchun joy soralmasa unda quyidagicha boladi 



def marge_list(arr1 : list[int], arr2 : list[int])->Iterable[int]:

    i = j = 0
    n , m  = len(arr1), len(arr2)

    while i < n and j< m :
        if arr1[i] < arr2[j]:
            yield arr1[i]
            i+= 1
        else:
            yield arr2[j]
            j += 1 


    while i < n :
        yield arr1[i]
        i += 1

    while j < m :
        yield arr2[j]
        j+= 1


arr3 = [1,2,4,6,8]
arr4 = [3,5,7,10,13,14]
print(list(marge_list(arr3 ,arr4)))