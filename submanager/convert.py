import base64
import json
import random
import string
from urllib.parse import urlparse, parse_qs
from fake_useragent import UserAgent
from submanager.util import get_http_proxies
from subscribe import utils
import yaml
import sys
import requests


# Utility functions
def unique_name(names, temp_name):
    if not temp_name:
        temp_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    count = names.get(temp_name, 0)
    names[temp_name] = count + 1
    if count == 0:
        return temp_name
    return f"{temp_name}_{count}"


def rand_user_agent():
    ua = UserAgent()
    return ua.random


# Base Proxy class
class Proxy:
    def __init__(self, name, proxy_type):
        self.name = name
        self.type = proxy_type

    def to_dict(self):
        return vars(self)

    @classmethod
    def parse(cls, line, names):
        raise NotImplementedError("Parse method not implemented.")


# Proxy classes for each type
class HysteriaProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            url = urlparse(line)
            query = parse_qs(url.query)
            name = unique_name(names, url.fragment)
            server = url.hostname
            port = url.port
            sni = query.get('peer', [''])[0]
            obfs = query.get('obfs', [''])[0]
            alpn = query.get('alpn', [''])[0].split(',') if query.get('alpn', [''])[0] else None
            auth_str = query.get('auth', [''])[0]
            protocol = query.get('protocol', [''])[0]
            up = query.get('up', [''])[0] or query.get('upmbps', [''])[0]
            down = query.get('down', [''])[0] or query.get('downmbps', [''])[0]
            skip_cert_verify = query.get('insecure', ['false'])[0].lower() == 'true'
            return cls(name, 'hysteria', server, port, sni, obfs, alpn, auth_str, protocol, up, down, skip_cert_verify)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, sni, obfs, alpn, auth_str, protocol, up, down, skip_cert_verify):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.sni = sni
        self.obfs = obfs
        self.alpn = alpn
        self.auth_str = auth_str
        self.protocol = protocol
        self.up = up
        self.down = down
        self.skip_cert_verify = skip_cert_verify


class Hysteria2Proxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            url = urlparse(line)
            query = parse_qs(url.query)
            name = unique_name(names, url.fragment)
            server = url.hostname
            port = url.port or 443
            obfs = query.get('obfs', [''])[0]
            obfs_password = query.get('obfs-password', [''])[0]
            sni = query.get('sni', [''])[0]
            skip_cert_verify = query.get('insecure', ['false'])[0].lower() == 'true'
            alpn = query.get('alpn', [''])[0].split(',') if query.get('alpn', [''])[0] else None
            password = url.username
            fingerprint = query.get('pinSHA256', [''])[0]
            down = query.get('down', [''])[0]
            up = query.get('up', [''])[0]
            ports = query.get('mport', [''])[0]
            return cls(name, 'hysteria2', server, port, obfs, obfs_password, sni, skip_cert_verify, alpn, password,
                       fingerprint, down, up, ports)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, obfs, obfs_password, sni, skip_cert_verify, alpn, password,
                 fingerprint, down, up, ports):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.obfs = obfs
        self.obfs_password = obfs_password
        self.sni = sni
        self.skip_cert_verify = skip_cert_verify
        self.alpn = alpn
        self.password = password
        self.fingerprint = fingerprint
        self.down = down
        self.up = up
        self.ports = ports


class TuicProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            url = urlparse(line)
            query = parse_qs(url.query)
            name = unique_name(names, url.fragment)
            server = url.hostname
            port = url.port
            udp = True
            uuid = None
            password = None
            token = None
            if url.password:
                uuid = url.username
                password = url.password
            else:
                token = url.username
            congestion_controller = query.get('congestion_control', [''])[0]
            alpn = query.get('alpn', [''])[0].split(',') if query.get('alpn', [''])[0] else None
            sni = query.get('sni', [''])[0]
            disable_sni = query.get('disable_sni', [''])[0] == '1'
            udp_relay_mode = query.get('udp_relay_mode', [''])[0]
            skip_cert_verify = query.get('allow_insecure', [''])[0] == '1'
            return cls(name, 'tuic', server, port, udp, uuid, password, token, congestion_controller, alpn, sni,
                       disable_sni, udp_relay_mode, skip_cert_verify)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, udp, uuid=None, password=None, token=None,
                 congestion_controller=None, alpn=None, sni=None, disable_sni=None, udp_relay_mode=None,
                 skip_cert_verify=None):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.udp = udp
        self.uuid = uuid
        self.password = password
        self.token = token
        self.congestion_controller = congestion_controller
        self.alpn = alpn
        self.sni = sni
        self.disable_sni = disable_sni
        self.udp_relay_mode = udp_relay_mode
        self.skip_cert_verify = skip_cert_verify


class TrojanProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            url = urlparse(line)
            query = parse_qs(url.query)
            name = unique_name(names, url.fragment)
            server = url.hostname
            port = url.port
            password = url.username
            udp = True
            skip_cert_verify = query.get('allowInsecure', ['false'])[0].lower() == 'true'
            sni = query.get('sni', [''])[0]
            alpn = query.get('alpn', [''])[0].split(',') if query.get('alpn', [''])[0] else None
            network = query.get('type', [''])[0].lower()
            ws_opts = None
            grpc_opts = None
            if network == 'ws':
                headers = {'User-Agent': rand_user_agent()}
                ws_opts = {'path': query.get('path', [''])[0], 'headers': headers}
            elif network == 'grpc':
                grpc_opts = {'grpc-service-name': query.get('serviceName', [''])[0]}
            fingerprint = query.get('fp', [''])[0] or 'chrome'
            return cls(name, 'trojan', server, port, password, udp, skip_cert_verify, sni, alpn, network, ws_opts,
                       grpc_opts, fingerprint)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, password, udp, skip_cert_verify, sni, alpn, network,
                 ws_opts=None, grpc_opts=None, client_fingerprint=None):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.password = password
        self.udp = udp
        self.skip_cert_verify = skip_cert_verify
        self.sni = sni
        self.alpn = alpn
        self.network = network
        self.ws_opts = ws_opts
        self.grpc_opts = grpc_opts
        self.client_fingerprint = client_fingerprint


class VlessProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            url = urlparse(line)
            query = parse_qs(url.query)
            name = unique_name(names, url.fragment)
            server = url.hostname
            port = url.port
            uuid = url.username
            udp = True
            tls = False
            skip_cert_verify = False
            encryption = query.get('encryption', [''])[0] or 'none'
            flow = query.get('flow', [''])[0]
            sni = query.get('sni', [''])[0]
            network = query.get('type', [''])[0].lower()
            ws_opts = None
            grpc_opts = None
            if network == 'ws':
                ws_opts = {'path': query.get('path', [''])[0], 'headers': {}}
            elif network == 'grpc':
                grpc_opts = {'grpc-service-name': query.get('serviceName', [''])[0]}
            return cls(name, 'vless', server, port, uuid, udp, tls, skip_cert_verify, encryption, flow, sni, network,
                       ws_opts, grpc_opts)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, uuid, udp, tls, skip_cert_verify, encryption, flow, sni, network,
                 ws_opts=None, grpc_opts=None):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.uuid = uuid
        self.udp = udp
        self.tls = tls
        self.skip_cert_verify = skip_cert_verify
        self.encryption = encryption
        self.flow = flow
        self.sni = sni
        self.network = network
        self.ws_opts = ws_opts
        self.grpc_opts = grpc_opts


class VmessProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        scheme, _, body = line.partition('://')
        body = body.strip()
        try:
            decoded = base64.urlsafe_b64decode(body + '===').decode('utf-8')
            values = json.loads(decoded)
            temp_name = values.get('ps')
            if not temp_name:
                return None
            name = unique_name(names, temp_name)
            server = values.get('add')
            port = int(values.get('port'))
            uuid = values.get('id')
            alterId = int(values.get('aid', 0))
            udp = True
            tls = False
            skip_cert_verify = False
            cipher = values.get('scy', 'auto')
            servername = values.get('sni', '')
            network = values.get('net', '').lower()
            if values.get('type') == 'http':
                network = 'http'
            elif network == 'http':
                network = 'h2'
            tls = values.get('tls', '').lower().endswith('tls')
            alpn = values.get('alpn', '').split(',') if values.get('alpn', '') else None
            ws_opts = None
            h2_opts = None
            http_opts = None
            grpc_opts = None
            if network == 'http':
                headers = {}
                host = values.get('host', '')
                if host:
                    headers['Host'] = [host]
                http_opts = {'path': [values.get('path', '/')], 'headers': headers}
            elif network == 'h2':
                headers = {}
                host = values.get('host', '')
                if host:
                    headers['Host'] = [host]
                h2_opts = {'path': values.get('path', ''), 'headers': headers}
            elif network in ['ws', 'httpupgrade']:
                headers = {}
                host = values.get('host', '')
                if host:
                    headers['Host'] = host
                ws_opts = {'path': values.get('path', '/'), 'headers': headers}
            elif network == 'grpc':
                grpc_opts = {'grpc-service-name': values.get('path', '')}
            return cls(name, 'vmess', server, port, uuid, alterId, udp, tls, skip_cert_verify, cipher, servername,
                       network, ws_opts, h2_opts, http_opts, grpc_opts, alpn)
        except Exception:
            try:
                url = urlparse(line)
                query = parse_qs(url.query)
                name = unique_name(names, url.fragment)
                server = url.hostname
                port = url.port
                uuid = url.username
                alterId = 0
                cipher = query.get('encryption', ['auto'])[0]
                return cls(name, 'vmess', server, port, uuid, alterId, True, False, False, cipher, None, None)
            except Exception:
                return None

    def __init__(self, name, proxy_type, server, port, uuid, alterId, udp, tls, skip_cert_verify, cipher, servername,
                 network, ws_opts=None, h2_opts=None, http_opts=None, grpc_opts=None, alpn=None):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.uuid = uuid
        self.alterId = alterId
        self.udp = udp
        self.tls = tls
        self.skip_cert_verify = skip_cert_verify
        self.cipher = cipher
        self.servername = servername
        self.network = network
        self.ws_opts = ws_opts
        self.h2_opts = h2_opts
        self.http_opts = http_opts
        self.grpc_opts = grpc_opts
        self.alpn = alpn


class SsProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            url = urlparse(line)
            name = unique_name(names, url.fragment)
            port = url.port
            cipher_raw = url.username
            cipher = cipher_raw
            password = url.password
            if not port or not password:
                decoded = base64.urlsafe_b64decode(cipher_raw + '===').decode('utf-8')
                cipher, password = decoded.split(':', 1)
            server = url.hostname
            query = parse_qs(url.query)
            udp = True
            udp_over_tcp = query.get('udp-over-tcp', [''])[0] == 'true' or query.get('uot', [''])[0] == '1'
            plugin = query.get('plugin', [''])[0]
            plugin_opts = {}
            if plugin:
                plugin_parts = plugin.split(';')
                plugin_name = plugin_parts[0]
                plugin_info = {}
                for part in plugin_parts[1:]:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        plugin_info[key] = value
                if 'obfs' in plugin_name:
                    plugin = 'obfs'
                    plugin_opts = {'mode': plugin_info.get('obfs'), 'host': plugin_info.get('obfs-host')}
                elif 'v2ray-plugin' in plugin_name:
                    plugin = 'v2ray-plugin'
                    plugin_opts = {
                        'mode': plugin_info.get('mode'),
                        'host': plugin_info.get('host'),
                        'path': plugin_info.get('path'),
                        'tls': 'tls' in plugin
                    }
            return cls(name, 'ss', server, port, cipher, password, udp, udp_over_tcp, plugin, plugin_opts)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, cipher, password, udp, udp_over_tcp=None, plugin=None,
                 plugin_opts=None):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.cipher = cipher
        self.password = password
        self.udp = udp
        self.udp_over_tcp = udp_over_tcp
        self.plugin = plugin
        self.plugin_opts = plugin_opts


class SsrProxy(Proxy):
    @classmethod
    def parse(cls, line, names):
        try:
            decoded = base64.urlsafe_b64decode(line[6:] + '===').decode('utf-8')
            before, sep, after = decoded.partition('/?')
            if not sep:
                return None
            before_arr = before.split(':')
            if len(before_arr) != 6:
                return None
            host = before_arr[0]
            port = before_arr[1]
            protocol = before_arr[2]
            method = before_arr[3]
            obfs = before_arr[4]
            password_enc = before_arr[5]
            password = base64.urlsafe_b64decode(password_enc + '===').decode('utf-8')
            query = parse_qs(after)
            remarks_enc = query.get('remarks', [''])[0]
            remarks = base64.urlsafe_b64decode(remarks_enc + '===').decode('utf-8')
            name = unique_name(names, remarks)
            obfs_param_enc = query.get('obfsparam', [''])[0]
            obfs_param = base64.urlsafe_b64decode(obfs_param_enc + '===').decode('utf-8') if obfs_param_enc else None
            protocol_param_enc = query.get('protoparam', [''])[0]
            protocol_param = base64.urlsafe_b64decode(protocol_param_enc + '===').decode(
                'utf-8') if protocol_param_enc else None
            return cls(name, 'ssr', host, port, method, password, obfs, protocol, True, obfs_param, protocol_param)
        except Exception:
            return None

    def __init__(self, name, proxy_type, server, port, cipher, password, obfs, protocol, udp, obfs_param=None,
                 protocol_param=None):
        super().__init__(name, proxy_type)
        self.server = server
        self.port = port
        self.cipher = cipher
        self.password = password
        self.obfs = obfs
        self.protocol = protocol
        self.udp = udp
        self.obfs_param = obfs_param
        self.protocol_param = protocol_param


# Mapping schemes to proxy classes
scheme_to_class = {
    'hysteria': HysteriaProxy,
    'hysteria2': Hysteria2Proxy,
    'hy2': Hysteria2Proxy,
    'tuic': TuicProxy,
    'trojan': TrojanProxy,
    'vless': VlessProxy,
    'vmess': VmessProxy,
    'ss': SsProxy,
    'ssr': SsrProxy,
}


def convert_link(link, names=None):
    if not names:
        names = {}

    scheme, sep, body = link.partition('://')
    if sep != '://':
        return ''
    scheme = scheme.lower()
    proxy_class = scheme_to_class.get(scheme)
    if proxy_class:
        proxy = proxy_class.parse(link, names)
        if proxy:
            return proxy.to_dict()
    return ''


# Function to convert links
def convert_links(links):
    proxies = []
    names = {}
    for line in links:
        scheme, sep, body = line.partition('://')
        if sep != '://':
            continue
        scheme = scheme.lower()
        proxy_class = scheme_to_class.get(scheme)
        if proxy_class:
            proxy = proxy_class.parse(line, names)
            if proxy:
                proxies.append(proxy.to_dict())
    return proxies


if __name__ == '__main__':
    url = 'https://raw.githubusercontent.com/leetomlee123/freenode/main/README.md'
    response = requests.get(url, headers=utils.DEFAULT_HTTP_HEADERS, proxies=get_http_proxies(), timeout=3)
    response.encoding = 'utf-8'
    lines = [x for x in response.text.splitlines() if '://' in x]
    proxies = convert_links(lines)
    yaml.dump(proxies, sys.stdout, allow_unicode=True)
