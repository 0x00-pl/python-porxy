import select
import socket
import time

request_pool={}
request_pool_empty_node={'recv':lambda x:None , 'err':lambda x:None}
recv_log=[]
entry= socket.socket()

class socket_reader:
    def __init__(self,sock):
        #print('init socket_reader')
        self.sock= sock
        self.data= b''

    def readline_crlf_y(self,dest_list):
        ptr_crlf= self.data.find(b'\r\n')
        #print('crlf find in', ptr_crlf)
        while ptr_crlf==-1 :
            yield
            new_data= self.sock.recv(1024)
            print('data recved:',new_data)
            if len(new_data)==0: 
                print('recv-empty-package!:')
                # todo some error raize #{output last line, end func}
                return
            self.data= self.data+ new_data
            ptr_crlf= self.data.find(b'\r\n')
        #print('set dest')
        dest_list.append(self.data[0:ptr_crlf+2])
        self.data= self.data[ptr_crlf+2:]
        return

def stop_link(a,b):
    a.close()
    b.close()
    request_pool.pop(a,None)
    request_pool.pop(b,None)
    
def recv_socket_pipe_y(skt):
    while True :
        data= skt.recv(1024)
        if len(data)==0 : return
        yield data
        
def recv_request_y(src_socket, dest_socket):
    req_header= {}

    # yield from read_header(src_socker,req_header) #feature in >=3.3
    for x in read_header_y(src_socker,req_header): yield #feature in <3.3

    if dest_socket==None :
        addr= make_dest_connection(req_header)
        yield
        dest_socket= socket.socket()
        dest_socket.connect(addr)
    res_header= {}

    # yield from read_header(dest_socket, res_header) #feature in >=3.3
    for x in read_header_y(src_socker,req_header): yield #feature in <3.3

    
    
    

def bind_socket_recv(dst,src):
    def retf(x):
        try:
            data= src.recv(1024)
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
    host_port= 80
    if temp_host_name_spl==-1 :
        temp_host_name_spl= len(host_name)
    else:
        host_port= int(host_name[temp_host_name_spl+1:])

    #recv_log.append({'event':'request','host':host_name,'host_port':host_port})
    print('request:',data_top[0:host_offset],'Host:',host_name)
    if len(host_name)<10 :
        print('waring revc unknow request:',[data_top])
        
    # make socket to host
    try:
        host_socket= socket.socket()
        host_socket.connect((host_name[0:temp_host_name_spl],host_port))
    except IOError:
        stop_link(host_socket,skt)
        return
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
    request_pool[conn]= {'recv':request_recv}

def start_server(port):    
    try:
        print('start_server; port:',port)
        entry.bind(('',port))
        entry.listen(10)
        request_pool[entry]= {'recv':entry_recv}
        
        while True:
            tgrecv,_,tgerr= select.select(request_pool.keys(),[],request_pool.keys(),0.1)
            [request_pool.get(x,request_pool_empty_node)['recv'](x) for x in tgrecv]
            [request_pool[x]['err'](x) for x in tgerr]

    except BaseException as e:
        entry.close()
        print('close entry')
        raise e

def readallline_y(src_socket):
    #print('make sr')
    sr= socket_reader(src_socket)
    #print('begin read')
    while True:
        res=[]
        for x in sr.readline_crlf_y(res):
            yield
        if len(res)==0 : 
            src_socket.close()
            return
        if res[0]==b'\r\n' : return
        print('getline:',res[0])

if __name__=='__main__':
    #start_server(8097)
    entry.bind(('',9109))
    entry.listen(1)
    conn,addr= entry.accept()
    conn.setblocking(False)
    print('start')
    yd=readallline_y(conn)
    next(yd,None)
    while True:
        rdr,_,_=select.select([conn],[],[],0)
        if len(rdr)>0 :
            print('selected',rdr)
            next(yd,None)
        #print('loop')


# TODO
# this version:
#  read the header
#
# 
# bug: recv 0 size request 
# # fix: close connet
#
# bug: port cannot close{
#   File "/tmp/py3921KEk", line 86, in start_server
#    entry.bind(('',port))
#  socket.error: [Errno 98] Address already in use
# }
# # fix: ignore
