import select
import socket
import time

request_pool={}
request_pool_empty_node={'recv':lambda x:None , 'err':lambda x:None}
recv_log=[]
entry= socket.socket()
def stop_link(a,b):
    a.close()
    b.close()
    request_pool.pop(a,None)
    request_pool.pop(b,None)
    
def bind_socket_recv(dst,src):
    def retf(x):
        try:
            data= src.recv(1024)
            print(data[0:512],'...')
            if len(data)==0 : 
                stop_link(dst,src)
                return
            dst.sendall(data)
        except IOError:
            print('error socket IOError; len(link):',len(request_pool))
            stop_link(dst,src)

    return retf

def bind_socket_err(a,b):
    def retf(x):
        stop_link(a,b)
        print('message socket link break; len(link):',len(request_pool))
    return retf

def request_recv(skt):
    data_top= skt.recv(1024)
    if len(data_top)==0 : 
        skt.close()
        request_pool.pop(skt,None)
        print('error recv empty request')
        return
    # get request methods
    request_methods= data_top[0:data_top.find(b' ')]
    # get host
    temp_bytes_host= b'\r\nHost: '
    host_offset= data_top.find(temp_bytes_host)+len(temp_bytes_host)
    if host_offset==-1 :
        print('error cannot find Host')
        #recv_log.append({'event':'request-format-error','data_top':data_top})
        return
    host_name= data_top[host_offset : data_top[host_offset:].find(b'\r\n')+host_offset]
    temp_host_name_spl= host_name.find(b':')    
    # default port
    host_port=-1
    if data_top.startswith(b'GET') :
        host_port= 80
    elif data_top.startswith(b'CONNECT'):
        host_port= 443
    else:
        print(data_top[0:10])

    if temp_host_name_spl==-1 :
        temp_host_name_spl= len(host_name)
    else:
        host_port= int(host_name[temp_host_name_spl+1:])

    #recv_log.append({'event':'request','host':host_name,'host_port':host_port})
    print('request:',data_top[0:host_offset],'Host:',host_name,'port:',host_port,'len',len(data_top))
    print(data_top)
    if len(host_name)<10 :
        print('waring revc unknow request:',[data_top])
        
    # make socket to host
    try:
        host_socket= socket.socket()
        print('connect: start!',(host_name[0:temp_host_name_spl],host_port))
        host_socket.connect((host_name[0:temp_host_name_spl],host_port))# error block
        print('connect: done!')
    except IOError as e:
        stop_link(host_socket,skt)
        print('connect: fail!',e)
        return
    host_socket.setblocking(False)
    # sent data_top
    host_socket.sendall(data_top)
    # link pipe-line
    request_pool[skt]={
    'recv': bind_socket_recv(host_socket,skt) ,
    'err': bind_socket_err(host_socket,skt)
    }
    request_pool[host_socket]={
    'recv': bind_socket_recv(skt,host_socket) ,
    'err': bind_socket_err(host_socket,skt)
    }

def entry_recv(skt):
    conn,addr= entry.accept()
    #recv_log.append({'event':'entry-accept', 'addr':addr})
    print('entry:',addr,'; len(link):',len(request_pool))
    #request_recv(conn)
    conn.setblocking(False)
    request_pool[conn]= {'recv':request_recv}

def start_server(port):    
    try:
        print('start_server; port:',port)
        entry.bind(('',port))
        entry.listen(10)
        request_pool[entry]= {'recv':entry_recv}
        entry.setblocking(False)
        while True:
            tgrecv,_,tgerr= select.select(request_pool.keys(),[],request_pool.keys(),0.1)
            [request_pool.get(x,request_pool_empty_node)['recv'](x) for x in tgrecv]
            [request_pool[x]['err'](x) for x in tgerr]

    except BaseException as e:
        entry.close()
        print('close entry')
        raise e

if __name__=='__main__':
    start_server(8098)

# TODO
# recv 0 size request
# port cannot close{
#   File "/tmp/py3921KEk", line 86, in start_server
#    entry.bind(('',port))
#  socket.error: [Errno 98] Address already in use
# }
