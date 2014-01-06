import time

def start():
    return {'start_time': time.time()}

def end(start_time, website):
    if website.log_metrics:
        print("count#requests=1")
        response_time = time.time() - start_time
        print("measure#response_time={}ms".format(response_time * 1000))
