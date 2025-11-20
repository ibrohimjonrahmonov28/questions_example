import timeit

def timer_function(func_call: str, number_loop: int, globs=None):
    """
    func_call_str : funksiya chaqiruvi string sifatida, masalan "sum_of_root(1000)"
    number_loop   : necha marta ishlashini o'lchash
    """
    if globs is None:
        import inspect
        globs = inspect.currentframe().f_back.f_globals
    second = timeit.timeit(
                            func_call,
                            globals=globs,
                            number=number_loop
                                                )
    return second
