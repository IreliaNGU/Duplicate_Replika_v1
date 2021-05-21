# -*- coding: utf-8 -*-
import socket
import time
from socket import *
import socketserver
import threading
import importlib, sys
import logging
from web import run
from enum import Enum

importlib.reload(sys)
address = '0.0.0.0'  # 监听哪些网络  127.0.0.1是监听本机 0.0.0.0是监听整个网络
port = 9999  # 监听自己的哪个端口
buffsize = 1024  # 接收从客户端发来的数据的缓存区大小
s = socket(AF_INET, SOCK_STREAM)
s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
s.bind((address, port))
s.listen(5)  # 最大连接数
NetTimeout = 60000

#设置接收超时
# s.setsockopt(SOL_SOCKET,SO_RCVTIMEO,NetTimeout)

#同时打开的线程数，打开两个以上会报connect refuse的错误
thread_num = 1
threads = []
#黑名单
BlackList = "blacklist.txt"
#日志记录
logging.basicConfig(level=logging.INFO,
                    filename='./log.txt',
                    filemode='w',
                    format='%(asctime)s : %(funcName)s : %(levelname)s : %(message)s')

#状态列表
class THREAD_STATE(Enum):
    stInit = 0
    stWaitConnect = 1
    stConnect = 2
    stLogin = 3
    stChat = 4
    stError = 5
    stFetch = 6
    stSave = 7

#为一个用户分配的线程
class UserDialogThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        print(u'Thread%s start to init.' % threading.current_thread().name)
        self.setState(THREAD_STATE.stInit)
        self.setEmpty()

    def terminate(self):
        self._running = False

    def setState(self, state):
        self.state = state

    def getState(self):
        return self.state

    def setConnect(self, clientsock, clientaddress):
        self.clientsock = clientsock
        self.clientaddress = clientaddress

    def set_email_and_password(self, email, password):
        self.email = email
        self.password = password

    def setDriver(self, driver):
        self.driver = driver

    def setListenerThread(self, thread):
        self.listener = thread

    def getListenerThread(self):
        return self.listener

    def setEmpty(self):
        self.driver = None
        self.email = None
        self.password = None
        self.listener = None
        self.clientsock = None
        self.clientaddress = None

    def run(self):
        while True:
            if self.state == THREAD_STATE.stInit:
                try:
                    driver = run.load_webpage()
                    self.setDriver(driver)
                    self.state = THREAD_STATE.stWaitConnect
                    print(threading.current_thread().name + ' is waiting for connect.')
                    logging.info(threading.current_thread().name + ' is waiting for connect.')
                except Exception as e:
                    print(threading.current_thread().name+' error in stInit: '+str(e))
                    logging.error(threading.current_thread().name+' error in stInit: '+str(e))
                    self.state = THREAD_STATE.stError
            elif self.state == THREAD_STATE.stWaitConnect:
                pass
            elif self.state == THREAD_STATE.stConnect:  # 已和APP建立网络连接
                try:
                    print(threading.current_thread().name + ' is ready for client: ' + str(self.clientaddress))
                    logging.info(threading.current_thread().name + ' is ready for client: ' + str(self.clientaddress))
                    recvdata = clientsock.recv(buffsize).decode('utf-8')
                    if not recvdata:
                        self.state = THREAD_STATE.stError
                    infos = recvdata.split('|', 1)
                    # print(infos)
                    # 确认为登录操作
                    if infos[0] == '0':
                        user_data = infos[1].split('|', 1)
                        self.set_email_and_password(user_data[0], user_data[1])
                        print(threading.current_thread().name + ' receive email: ' + self.email)
                        print(threading.current_thread().name + ' receive password: ' + self.password)
                        logging.info(threading.current_thread().name + ' receive email: ' + self.email)
                        logging.info(threading.current_thread().name + ' receive password: ' + self.password)
                        self.state = THREAD_STATE.stLogin
                    else:
                        self.state = THREAD_STATE.stError
                        print(threading.current_thread().name + ' receive a not login message,operate code: ' +
                              infos[0])
                        logging.error(threading.current_thread().name + ' receive a not login message,operate code: ' +
                              infos[0])
                        #逮到一个非法IP，写入黑名单中
                        bl = open(BlackList, "a+")
                        logging.info("Write "+str(self.clientaddress[0])+" to black list.")
                        bl.write(str(self.clientaddress[0])+'\n')
                        bl.close()
                except Exception as e:
                    print(threading.current_thread().name + ' error in stConnect: ' + str(e))
                    logging.error(threading.current_thread().name + ' error in stConnect: ' + str(e))
                    self.state = THREAD_STATE.stError
            elif self.state == THREAD_STATE.stLogin:
                try:
                    result = run.login(self.driver, self.email, self.password)
                    if result == 'success':
                        self.clientsock.send(result.encode())
                        self.state = THREAD_STATE.stFetch
                    else:
                        print(threading.current_thread().name + ' :login in fail.Because '+ result)
                        logging.error(threading.current_thread().name + ' :login in fail.Because '+ result)
                        self.clientsock.send(result.encode())
                        self.state = THREAD_STATE.stError
                        time.sleep(5)
                        # 重新登录或者给APP发送错误信息
                        pass
                except Exception as e:
                    print(threading.current_thread().name + ' error in stLogin: ' + str(e))
                    logging.error(threading.current_thread().name + ' error in stLogin: ' + str(e))
                    self.state = THREAD_STATE.stError
            elif self.state == THREAD_STATE.stFetch:
                try:
                    history = run.fetch_history(self.driver)
                    self.clientsock.send(history.encode())
                    self.state = THREAD_STATE.stChat
                except Exception as e:
                    print(threading.current_thread().name + ' error in stFetch: ' + str(e))
                    logging.error(threading.current_thread().name + ' error in stFetch: ' + str(e))
                    self.state = THREAD_STATE.stError
            elif self.state == THREAD_STATE.stChat:
                try:
                    if not self.getListenerThread():
                        # 打开一个监听线程
                        print(threading.current_thread().name + ' open a listener thread to check '
                                                                'message from replika.')
                        logging.info(threading.current_thread().name + ' open a listener thread to check '
                                                                'message from replika.')
                        t=run.Listener_Thread(self.driver,self.clientsock,self.email)
                        self.setListenerThread(t)
                        t.start()
                    msg_from_client = self.clientsock.recv(buffsize).decode('utf-8')
                    if not msg_from_client:
                        continue
                    infos = msg_from_client.split('|', 1)
                    if infos[0] == '1':
                        print(threading.current_thread().name + ' receive a chat message from client: '
                              + str(self.clientsock))
                        logging.info(threading.current_thread().name + ' receive a chat message from client: '
                              + str(self.clientsock))
                        run.send_message(self.driver, infos[1])
                    elif infos[0] == '-1':
                        print(threading.current_thread().name + ' receive a exit code from client: '
                              + str(self.clientsock))
                        logging.info(threading.current_thread().name + ' receive a exit code from client: '
                              + str(self.clientsock))
                        if self.getListenerThread():
                            logging.info('stChat close listener.')
                            self.getListenerThread().setStop()
                            self.getListenerThread().join()
                            self.listener=None
                        self.state = THREAD_STATE.stSave
                    else:
                        print(threading.current_thread().name + ' receive a not recognizable message,operate code: ' +
                              infos[0])
                        logging.error(threading.current_thread().name + ' receive a not recognizable message,operate code: ' +
                              infos[0])
                except Exception as e:
                    print(threading.current_thread().name + ' error in stChat: ' + str(e))
                    logging.error(threading.current_thread().name + ' error in stChat: ' + str(e))
                    self.state = THREAD_STATE.stError
            elif self.state == THREAD_STATE.stSave:
                logging.info('into stSave.')
                try:
                    #保存日志
                    run.save_history(self.driver)
                    self.state = THREAD_STATE.stError
                except Exception as e:
                    print(threading.current_thread().name + ' error in stSave: ' + str(e))
                    logging.error(threading.current_thread().name + ' error in stSave: ' + str(e))
                    self.state = THREAD_STATE.stError
            elif self.state == THREAD_STATE.stError:
                logging.info('Into stError.')
                try:
                    if self.getListenerThread():
                        logging.info('stError close listener.')
                        self.getListenerThread().setStop()
                        self.getListenerThread().join()
                    # 关闭与客户端连接
                    self.clientsock.close()
                    logging.info('close clientsock.')
                    #关闭浏览器
                    run.quit(self.driver)
                    logging.info('close driver.')
                    self.setEmpty()
                    self.state = THREAD_STATE.stInit
                    time.sleep(10)
                    print(threading.current_thread().name + ' is preparing for next connection')
                    logging.info(threading.current_thread().name + ' is preparing for next connection')
                except Exception as e:
                    print(threading.current_thread().name + ' error in stError: ' + str(e))
                    logging.error(threading.current_thread().name + ' error in stError: ' + str(e))
                    self.state = THREAD_STATE.stInit


def select_available_thread():
    for thread in threads:
        if thread.getState() == THREAD_STATE.stWaitConnect:
            thread.setConnect(clientsock,clientaddress)
            thread.setState(THREAD_STATE.stConnect)
            return 1
    print('Server:no available thread.')
    logging.info('Server:no available thread.')
    return 0


def check_and_stuck():
    while True:
        for thread in threads:
            if thread.getState() == THREAD_STATE.stWaitConnect:
                return
        logging.info('stuck.')
        time.sleep(5)

if __name__ == '__main__':
    while thread_num > 0:
        t = UserDialogThread()
        t.start()
        threads.append(t)
        thread_num -= 1
    while True:
        thread_i = 1
        fail_flag = 0
        for thread in threads:
            if thread.getState() == THREAD_STATE.stWaitConnect:
                thread_i += 1
                continue
            elif thread.getState() == THREAD_STATE.stInit:
                print('user thread '+str(thread_i)+' is initing.')
                logging.info('user thread '+str(thread_i)+' is initing.')
                thread_i += 1
                fail_flag += 1
            elif thread.getState() == THREAD_STATE.stError:
                print('user thread '+str(thread_i)+' is error.')
                logging.critical('user thread '+str(thread_i)+' is error.')
                thread_i += 1
                fail_flag += 1
            else:
                print('something get wrong.')
                logging.error('something get wrong.')
                thread_i += 1
                fail_flag +=1
        if not fail_flag:
            break
        else:
            print('There are '+str(fail_flag)+' user threads not ready.')
            logging.info('There are '+str(fail_flag)+' user threads not ready.')
        time.sleep(10)

    print('--------------START TO ACCEPT CLIENT--------------')
    logging.info('--------------START TO ACCEPT CLIENT--------------')
    #不断接收新的客户端请求
    while True:
        clientsock, clientaddress = s.accept()
        blackIP = 0
        #查看黑名单是否有这个IP,有的话直接close连接
        bl = open(BlackList,'r')
        while True:
            line = bl.readline()
            if not line:
                break
            line = line.strip('\n')
            if line == str(clientaddress[0]):
                logging.info('Catch a bad IP: '+ str(clientaddress[0]))
                clientsock.close()
                blackIP = 1
                break
        bl.close()
        if blackIP==1:
            continue
        print('connect from:'+ str(clientaddress))
        logging.info('connect from:'+ str(clientaddress))
        # 没有空闲的线程
        if not select_available_thread():
            clientsock.send("exit".encode())
            time.sleep(1)
            clientsock.close()
        # # 检查是否有空闲的线程，没有则堵塞，不接受新的请求
        # check_and_stuck()


