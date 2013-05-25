import logging
import socket
import subprocess
import time

class Docker(object):
    docker_id_length = 12
    port_in=5000 
    port_out=4000
    
    def __init__(self, docker_instance, ports_to_open=[]):
        ports_to_open += [self.__class__.port_in, self.__class__.port_out]

        # Build the docker command; add all desired open ports        
        docker_cmd  = ["docker", "run", "-i", "-t"]
        for p in ports_to_open:
            docker_cmd += ["-p", str(p)]
        docker_cmd += [docker_instance, "/bin/bash"]
        docker_cmd += ["-c", """hostname; nc -l %d | /bin/bash 2>&1 | nc -l %d""" % (self.__class__.port_in, self.__class__.port_out)]
        
        # start the docker, and listen for commands over TCP
        self.p = subprocess.Popen(docker_cmd, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        # read the ID
        self.ID = self.p.stdout.read(self.__class__.docker_id_length)

        # read the external port numbers being mapped to the internal ports
        self.port_map = {}
        for p in ports_to_open:
            self.port_map[p] = subprocess.Popen(["docker", "port", self.ID, str(p)], shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE).communicate()[0].strip()

        # open a socket to write in commands
        self.s_in = socket.create_connection(("localhost", self.port_map[self.__class__.port_in]))

        # open a socket to read out responses
        self.s_out = socket.create_connection(("localhost",  self.port_map[self.__class__.port_out]))
        self.s_out.setblocking(0)

    def run_command(self, cmd, block_for_output=None, wait_time=None):
        """ Run a command in the docker via the sockets, delaying before reading the response """
        #import pdb; pdb.set_trace()
        if block_for_output is None:
            block_for_output = wait_time is None

        assert not block_for_output or not wait_time, "Either run async or, if blocking, don't specify a wait time"""
        
        logging.debug(cmd.strip() + "\n")
        self.write_stdin(cmd.strip() + "\n")
        if block_for_output:
            return self.wait_for_read()
        else:
            return self.read_stdout(wait_time=wait_time)
    
    
    def stream_command(self, cmd, wait_time=1, wait_step=0.1):
        self.run_command(cmd=cmd, block_for_output=False, wait_time=0)
        self.stream_stdout(wait_time=wait_time, wait_step=wait_step)
        
    def stream_stdout(self, wait_time=1, wait_step=0.1):
        all_out = ""
        try:
            for i in range(int(round(wait_time/wait_step))):
                strout = self.read_stdout(wait_time=wait_step).strip()
                print strout,
                all_out += strout
        except Exception as e:
            self.close()
            raise e     
        return all_out   
            
    def write_stdin(self, input):
        """ Write commands to the container's shell input """
        try:
            self.s_in.send(input.strip() + "\n")
        except Exception as e:
            self.close()
            raise e
                
    def read_stdout(self, bytes=1000000, wait_time=0):
        """ Read from the contents of the response buffer """
        try:
            time.sleep(wait_time)
            return self.s_out.recv(bytes)
        except Exception as e:
            if hasattr(e, 'errno') and e.errno==11 and hasattr(e, 'strerror') and e.strerror=="Resource temporarily unavailable":
                return ""
            else:
                self.close()
                raise e

    def wait_for_read(self, wait_step=0.1, wait_time=100):
        """Wait for output; return when no new output comes"""

        strout = ""
        
        for i in range(int(round(wait_time/wait_step))):
            new_out = self.read_stdout(wait_time=0.1)
            if not strout:
                strout = new_out
            elif new_out:
                strout += new_out
            else:
                break;
        
        return strout
    
    def close(self):
        """ Kill the running docker container """
        if self.p:
            subprocess.Popen(["docker", "kill", self.ID]).communicate()
            self.s_in.close()
            self.s_out.close()

            self.p = None
            self.s_in = None
            self.s_out = None
            
            
    def __del__(self):
        self.close()


if __name__=="__main__":
    import signal
    logging.getLogger().level = logging.DEBUG
    
    ka_internal_port = 8024
    
    d = Docker("ka-lite-installed", ports_to_open=[ka_internal_port])
    print d.port_map
    
    print d.run_command("cd /ka-lite/kalite", wait_time=0.1)
    print d.run_command("ls -l")
#    print d.run_command("python manage.py syncdb --migrate", wait_time=10)
#    print d.run_command("python manage.py runserver %d" % ka_internal_port, wait_time=10)
    
    d.close()
    