"""
The main goal of this project is to create a handy, automated deployment tool based on SSH.
To put it simply, it will have to deploy Docker containers on a remote host, and therefore configure it appropriately beforehand.
"""
import argparse
import re
import paramiko
import sys
import threading
import time
from os import listdir
from os.path import isfile, join


class deployer:
    """ deployer prog """

    def __init__(self):
        """ initialisation """
        self.args = None
        self.v = False
        self.path = "./export/"

    def init(self):
        """ argument parsing and checking """
        def ip_regex(arg_value, pat=re.compile(r"^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$")):
            """ check ip format """
            if not pat.match(arg_value):
                raise argparse.ArgumentTypeError(f'{arg_value} is not a valid IPv4 adress')
            return arg_value

        parser = argparse.ArgumentParser()
        commands = ['config', 'initiate', 'build', 'deploy', 'healthcheck', 'all', 'restart']
        parser.add_argument("COMMAND", choices=commands, help="The command to exec")
        parser.add_argument("REMOTE_IP", type=ip_regex, help="A valid IPv4 adress")
        parser.add_argument("-u", "--user", default="root", help="User used to initiate connection")
        parser.add_argument("-p", "--pass", default="root", help="Password used to initiate connection")
        parser.add_argument("-i",  default=None, help="Identity file used to initiate connection")
        parser.add_argument("-v", "--verbose", action='store_true', help="verbose")
        parser.add_argument("SERVICE", nargs="*", help="The service to interact with" )
        args = vars(parser.parse_intermixed_args())
        args['SERVICE'] =  [] if not args['SERVICE'] else args['SERVICE']
        if args['COMMAND'] == 'deploy' and len(args['SERVICE']) == 0:
            parser.error("The 'deploy' command requires at least one service id")
        if args['COMMAND'] == 'config' and len(args['SERVICE']) != 0:
            parser.error("The 'config' does not take any service id as argument")
        self.v = args['verbose']
        self.args = args

    def command(self, command = None):
        """ launching command """
        if command is None:
            command = self.args["COMMAND"]
        c = {
             'config': self.config,
             "initiate": self.initiate,
             "build": self.build,
             "deploy": self.deploy,
             "all": self.all,
             "healthcheck": self.healthcheck,
             "restart": self.restart
            }[command]()
        self.ssh_exec(c)

    def ssh_exec(self, command):
        """ executing bash command throught ssh """
        fix = "echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections"
        command = [fix] + [i for i in map(str.strip, command.split('\n')) if i != '']
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        t = self.printa("Connecting")
        ssh.connect(self.args["REMOTE_IP"], username=self.args["user"], password=self.args["pass"], key_filename=self.args['i'])
        t.kill()
        ret = []
        if not self.v:
            t = self.printa("Executing")
        for i in command:
            if self.v:
                t1 = self.printa(f"Executing {i}", True)
            stdin, stdout, stderr = ssh.exec_command(i)
            err = '\n'.join(stderr.readlines())[:-1]
            log = ''.join(stdout.readlines())
            ret.append(
                {
                    "command": i,
                    "stdout": log.split('\n')[:-1],
                    "stderr": err
                }
            )
            if self.v:
                t1.kill()
                time.sleep(0.2)
            if err != '':
                t.kill()
                print(f"ERROR: while executing '{i}': {err  }")
                break
            self.printf(f"$> {i}\n{log + err}")

        t.kill()
        t = self.printa("Disconnecting")
        ssh.close()
        t.kill()

    def printf(self, s):
        """ print if verbose """
        if self.v:
            print(s)

    def printa(self, s, r = False):
        """ print async message with animation """
        t = self.Wait(s, r)
        t.start()
        return t

    def all(self):
        """ run all command """
        return self.initiate() + self.build() + self.deploy() + self.healthcheck()

    def config(self):
        """ config """
        command =   """
                        apt-get update
                        apt-get install -y apt-transport-https ca-certificates curl
                        curl -fsSL "https://download.docker.com/linux/debian/gpg" | APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=true apt-key add -
                        echo "deb [arch=amd64] https://download.docker.com/linux/debian stretch stable" > /etc/apt/sources.list.d/docker.list
                        apt-get update
                        apt-get install -y --no-install-recommends docker-ce
                        docker version
                    """
        return command

    def initiate(self):
        """ scp """
        command =  f"""
                      rm -rf {self.path}
                      mkdir -p {self.path}
                   """
        files = [f for f in listdir(self.path) if isfile(join(self.path, f))]
        for i in files:
            f = open(self.path + i, "r")
            d = f.read().replace('\n', '\\n').replace("\"", "\\\"")
            f.close()
            command +=  f"\necho -e \"{d}\" > {self.path}{i}\n"
        command += f"ls {self.path}"
        return command

    def build(self):
        """ docker build """
        serv = ['api', 'test'] if self.args["SERVICE"] == [] else self.args["SERVICE"]
        command =  ""
        for i in serv:
            command += f"""
                            docker build -t {i} -f {self.path}{i} {self.path}
                        """
        return command

    def deploy(self):
        """ docker run """
        serv = ['api', 'test'] if self.args["SERVICE"] == [] else self.args["SERVICE"]
        command =  ""
        for i in serv:
            command += f"""
                            [ "$(docker ps -a | grep {i})" ] && docker stop {i} && docker rm {i}
                            [ ! "$(docker ps -a | grep {i})" ] && $(head -n 1 {self.path}{i} | cut -c2-) -d --name {i} {i} && sleep 3 && docker logs {i} 2>&1
                        """
        return command

    def healthcheck(self):
        """ docker inspect """
        serv = ['api', 'test'] if self.args["SERVICE"] == [] else self.args["SERVICE"]
        command =  ""
        for i in serv:
            command += f"""
                            [ "$(docker ps -a | grep {i})" ] && docker inspect {i}  | jq '.[].State.Health'
                       """
        return command

    def restart(self):
        """ docker restart """
        serv = ['api', 'test'] if self.args["SERVICE"] == [] else self.args["SERVICE"]
        command =  ""
        for i in serv:
            command += f"""
                            [ "$(docker ps -a | grep {i})" ] && docker restart {i}
                       """
        return command

    class Wait(threading.Thread):
        """ thread class used for animation """
        def __init__(self, s, r = False):
            """init"""
            super().__init__()
            self._kill = threading.Event()
            self.message = s
            self.remove = r

        def run(self):
            """ run the animation """
            animation = "|/-\\"
            p = True
            while p:
                for i in range(4):
                    time.sleep(0.1)
                    sys.stdout.write(f"\r{self.message} {animation[i % len(animation)]}")
                    sys.stdout.flush()
                    is_killed = self._kill.wait(0.1)
                    if is_killed:
                        p = False
                        break
            if self.remove:
                p = "\r" * (len(self.message) + 3)

            else:
                p = f"\r{self.message} - Done\n"
            sys.stdout.write(p)
            sys.stdout.flush()

        def kill(self):
            """ kill the thread """
            self._kill.set()

if __name__ == '__main__':
    D = deployer()
    D.init()
    D.command()
