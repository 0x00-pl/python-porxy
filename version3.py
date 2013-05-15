import select
import socket
import time
import queue
import threading

debug_info=False
socket_using=0
wt_recv=0
wt_send=1
select_pool=[]
dns_pool={}
# [((wt_xxxx,skt),yed)]
entry= socket.socket()

def select_pool_add(yed):
    sign= next(yed,None)
    if sign!=None : 
        global select_pool
        select_pool.append((sign,yed))

class socket_reader:
    def __init__(self,sock):
        #print('init socket_reader')
        self.sock= sock
        self.data= b''
        
    def send(self,data):
        return self.sock.send(data)

    def recv(self,length):
        return self.sock.recv(length)

    def recv_y(self,length,dest_list):# (in,out)
        while len(self.data)<length :
            yield (st_recv,self.sock)
            new_data= self.sock.recv(length-len(self.data)) 
            if len(new_data)==0: 
                dest_list.append(self.data)
                self.data=b''
                return
            self.data= self.data+ new_data
        dest_list.append(self.data[0:length])
        self.data= self.data[length:]
        return
        

    def readline_crlf_y(self,dest_list):# (out)
        ptr_crlf= self.data.find(b'\r\n')
        #print('crlf find in', ptr_crlf)
        while ptr_crlf==-1 :
            yield (wt_recv,self.sock)
            new_data= self.sock.recv(65536)
            #print('data-recved:',new_data)
            if len(new_data)==0: 
                #print('recv-empty-package!:')
                dest_list.append(self.data)
                self.data=b''
                return
            self.data= self.data+ new_data
            ptr_crlf= self.data.find(b'\r\n')
        #print('set dest')
        dest_list.append(self.data[0:ptr_crlf+2])
        self.data= self.data[ptr_crlf+2:]
        return

def read_header_y(src_socket_reader,req_header):#(in,out)
    print('read hreader...')
    while True:
        res=[]
        for x in src_socket_reader.readline_crlf_y(res): yield x #yield from ...
        if len(res[0])==0 : 
            print('read header done.(get 0)')
            return
        req_header.append(res[0])
        if res[0]==b'\r\n' : 
            print('read header done.')
            return
dns_lookup_request=queue.Queue()
def dns_lookup_thread():
    while True:
        host_name= dns_lookup_request.get()
        start_time= time.time()
        host_addr= socket.gethostbyname(host_name)
        dns_pool[host_name]= host_addr
        dns_lookup_request.task_done()
        end_time= time.time()
        print('get dns-map:',host_name,host_addr, '  time:',end_time-start_time)
        
def dns_lookup(host_name):
    host_addr= dns_pool.get(host_name, None)
    if host_addr==None :
        dns_lookup_request.put_nowait(host_name)
        host_addr='127.0.0.1'
    return host_addr

def make_dest_connection(req_header,def_port):
    try:
        global socket_using
        for line in req_header:
            if line.startswith(b'Host:'):
                addr= list(line[:-2].split()[1].split(b':'))
                addr.append(def_port)
                host_name= addr[0]
                addr[0]= dns_lookup(host_name)
                socket_using=socket_using+1;
                conn= socket.socket()
                conn.setblocking(False)
                try:
                    if debug_info: print('connecting server...', (addr[0],int(addr[1])))
                    conn.connect((addr[0],int(addr[1])))
                except socket.error as e:
                    if debug_info: print('connecting server...done.',e)
                if debug_info: print('connecting server...done.')
                return conn
    except IndexError:
        print('requst-format-error: bad host')
        print('trace',req_header)

def simple_pipe_y(src_socket_reader,dest_socket_reader):#(in,in)
    if debug_info:print('connect pipe start...',end='')
    try:
        global socket_using
        while True :
            if debug_info:print('done.')
            yield (wt_recv,src_socket_reader.sock)
            if debug_info:print('simple-pipe-recv... ',end='')
            data= src_socket_reader.sock.recv(1<<20)
            if(len(data)<=0):
                src_socket_reader.sock.close()
                dest_socket_reader.sock.close()
                socket_using=socket_using-2
                if debug_info:print('connection: recv0 close pipe  ')
                return
            while len(data)>0 :
                yield (wt_send,dest_socket_reader.sock)
                length= dest_socket_reader.send(data)
                data= data[length:]
    except socket.error as e:
        src_socket_reader.sock.close()
        dest_socket_reader.sock.close()
        socket_using=socket_using-2
        if debug_info:print('connection: break in pipe',e)
        
def pipe_length_y(src_socket_reader, dest_socket_reader, length):#(in,in,in)
    if debug_info:print('pipe-length-start...',end='')
    while length>0 :
        if debug_info:print('done.')
        yield (wt_recv,src_socket_reader.sock)
        if debug_info:print('pipe-length...',end='')
        data= src_socket_reader.recv(length)
        length= length- len(data)
        
        while len(data)>0 :
            yield (wt_send,dest_socket_reader.sock)
            len_send= dest_socket_reader.send(data)
            data= data[len_send:]
        
def pipe_chuncked_y(src_socket_reader, dest_socket_reader):#(in,in)
    while True :
        line=[]
        for x in src_socket_reader.readline_crlf_y(line): yield x #yield from ...
        chunck_size= int(line[1])
        if(chunck_size==0):
            return
        for x in pipe_length_y(src_socket_reader, dest_socket_reader, chunck_size): yield x #yield from ...

def recv_request_y(src_socket_reader, dest_socket_reader):# (in,out)
    keep_alive= True
    while keep_alive :
        print('recving request ...')
        req_header= []
        for x in read_header_y(src_socket_reader,req_header): yield x #yield from

        if len(req_header)==0 :
            return
        # make dest connection
        if dest_socket_reader.sock==None :
            if req_header[0].startswith(b'CONNECT') :
                conn= make_dest_connection(req_header,443)
            else:
                conn= make_dest_connection(req_header,80)
            
            dest_socket_reader.sock= conn
            print('connection made')
            select_pool_add(simple_pipe_y(dest_socket_reader,src_socket_reader))
        
        # if keep-alive
        keep_alive= len([ 1 for x in req_header if x.startswith(b'Connection: Keep-Alive') ])!=0

        #send header
        print('sending header ...')
        if req_header[0].startswith(b'CONNECT') :
            None
        else:
            send_header=b''
            #translte from abs path # debug disable
            target= req_header[0].split(b' ',1)
            if target[1].startswith(b'http') :
                send_header= target[0]+b' /'+target[1].split(b'/',3)[3]
            else:
                send_header= req_header[0]

            for line in req_header[1:] :
                send_header= send_header+ line

            #print('send-header:',str(send_header))
            while len(send_header)>0 :
                yield (wt_send,dest_socket_reader.sock)
                length= dest_socket_reader.send(send_header)
                send_header= send_header[length:]

        # send body
        print('sending body ...')
        if req_header[0].startswith(b'CONNECT') :
            yield (wt_send,src_socket_reader.sock)
            src_socket_reader.send(b'200 OK Connection Established\r\n\r\n')
            select_pool_add(simple_pipe_y(src_socket_reader,dest_socket_reader))
            return
        else:
            chuncked= len([ 1 for x in req_header if x.startswith(b'Transfer-Encoding: chunked') ]) != 0 
            content_length_lines= [ x for x in req_header if x.startswith(b'Content-Length:') ]
            if chuncked :
                for x in pipe_chuncked_y(src_socket_reader,dest_socket_reader): yield x #yield from ...
            elif len(content_length_lines) != 0 :
                # Content-Length:
                content_length= int(content_length_lines[0].split()[1])
                print('sending content size',content_length, end='...')
                for x in pipe_length_y(src_socket_reader,dest_socket_reader,content_length): yield x #yield from ...
                print(content_length,'done')
            else:
                None
        print('sending request done!')
  

def entry_recv_y():
    print('entry-start...',end='')
    global socket_using
    while True :
        print('done.')
        yield (wt_recv,entry)
        print('entry-recv...',end='')
        conn,addr= entry.accept()
        socket_using=socket_using+1
        print('entry:',addr,'socket using', socket_using)
        conn.setblocking(False)
        select_pool_add(recv_request_y(socket_reader(conn),socket_reader(None)))

def start_server(port):    
    try:
        global select_pool
        global socket_using
        threading.Thread(target=dns_lookup_thread).start()
        print('start_server; port:',port)
        entry.bind(('',port))
        entry.listen(5)
        select_pool_add(entry_recv_y())
        
        while True:
            if debug_info:print('get socket from pool ... ',end='')
            brecv= {}
            bsend= {}
            for x in select_pool:
                if x[0][0]==wt_recv and x[0][1].fileno()>0:
                    brecv[x[0][1]]= x
            for x in select_pool:
                if x[0][0]==wt_send and x[0][1].fileno()>0:
                    bsend[x[0][1]]= x
            if debug_info:print('(%d,%d)done.'%(len(brecv),len(bsend)))
            print('selecting...',end='')
            tgrecv,tgsend,_= select.select(brecv.keys(),bsend.keys(),[],5)
            print('selecting(%d,%d)done.'%(len(tgrecv),len(tgsend)))
            #print('select %d,%d in %d,%d from %d'%(len(tgrecv),len(tgsend),len(brecv),len(bsend),len(select_pool)))
            if len(select_pool)>100 :print('pool size:',len(select_pool))
            if(len(tgrecv)>0 or len(tgsend)>0):
                select_pool=[]
                for x in tgrecv :
                    try:
                        temp= brecv.pop(x,None)
                        sign= next(temp[1],None)
                        if sign!=None :
                            brecv[x]=(sign,temp[1])
                    except socket.error as e:
                        print('connection: break in server loop recv',e,x.fileno())
                        x.close()
                        socket_using=socket_using-1
                for x in tgsend :
                    try:
                        temp= bsend.pop(x,None)
                        sign= next(temp[1],None)
                        if sign!=None :
                            bsend[x]=(sign,temp[1])
                    except socket.error as e:
                        print('connection: break in server loop send',e,x.fileno())
                        x.close()
                        socket_using=socket_using-1

                if debug_info:print('flip pool ... ',end='')
                [select_pool.append(x) for x in brecv.values()]
                [select_pool.append(x) for x in bsend.values()]
                if debug_info:print('done.')
                #print('new-len:',len(select_pool))
    except BaseException as e:
        #entry.close()
        print('close entry')
        raise e
    print('end')

if __name__=='__main__':
    port= int(input('port:'))
    start_server(port)


# TODO
# this version:
#  
# DONE
# # test new prog struct{ select+yield }
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
