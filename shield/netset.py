"""Fast lookups in large lists of networks (thousands of CIDRs): merged integer ranges searched with bisect."""
import ipaddress
from bisect import bisect_right

# Never block these, whatever a list says: private, loopback, link-local, shared (CGNAT), test and multicast
# ranges. FireHOL level1 includes them on purpose (bogons), and blocking them would lock out the server itself.
RESERVED = ["0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
            "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/3",
            "::/8", "fc00::/7", "fe80::/10", "ff00::/8", "2001:db8::/32"]


def parse_ip(value):
    try:
        return ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None


def parse_net(value):
    try:
        return ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError:
        return None


def is_public(ip):
    ip = ip if not isinstance(ip, str) else parse_ip(ip)
    return bool(ip) and ip.is_global and not ip.is_multicast


def _ranges(nets):
    out = {4: [], 6: []}
    for n in nets:
        out[n.version].append((int(n.network_address), int(n.broadcast_address)))
    for v in out:
        merged = []
        for a, b in sorted(out[v]):
            if merged and a <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        out[v] = merged
    return out


def _subtract(ranges, holes):
    out = []
    for a, b in ranges:
        parts = [(a, b)]
        for ha, hb in holes:
            nxt = []
            for pa, pb in parts:
                if hb < pa or ha > pb:
                    nxt.append((pa, pb))
                    continue
                if pa < ha:
                    nxt.append((pa, ha - 1))
                if hb < pb:
                    nxt.append((hb + 1, pb))
            parts = nxt
        out.extend(parts)
    return out


class NetSet:
    """Set of networks; `"1.2.3.4" in netset`. Reserved ranges (and any `exclude` networks) are cut out."""

    def __init__(self, items=(), exclude=()):
        nets = [n for n in (parse_net(i) for i in items) if n]
        holes = _ranges([n for n in (parse_net(i) for i in list(RESERVED) + list(exclude)) if n])
        self._r = {v: _subtract(r, holes[v]) for v, r in _ranges(nets).items()}
        self._starts = {v: [a for a, _ in r] for v, r in self._r.items()}

    def __contains__(self, ip):
        ip = parse_ip(ip) if isinstance(ip, str) else ip
        if ip is None:
            return False
        n = int(ip)
        starts = self._starts[ip.version]
        i = bisect_right(starts, n) - 1
        return i >= 0 and self._r[ip.version][i][1] >= n

    def __len__(self):
        return len(self._r[4]) + len(self._r[6])

    def addresses(self):
        return sum(b - a + 1 for a, b in self._r[4])
