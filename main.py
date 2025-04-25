import streamlit as st
import networkx.drawing as nxd
from netaddr import EUI
import io

# Set the Streamlit page configuration
# This sets the title and icon for the Streamlit app.
st.set_page_config(page_title="Spanning Tree Protocol (STP) Simulator", 
                   page_icon="🔄")

# --- STP Classes ---
# BPDU: Represents a Bridge Protocol Data Unit used in STP.
class BPDU(object):
    def __init__(self, root, cost, id, port):
        self.root = root
        self.cost = cost
        self.id = id
        self.port = port
        
    def getBest(self, other):
        if not other:
            return self
        return self if (self.root, self.cost, self.id, self.port) <= (other.root, other.cost, other.id, other.port) else other

    def __str__(self):
        return f"[{hex(self.root)}, {self.cost}, {hex(self.id)}, {self.port}]"

# Port: Represents a network port with STP roles and states.
class Port(object):
    ROLE_ROOT = "Root Port"
    ROLE_UNDESG = "Undesignated"
    ROLE_DESG = "Designated"
    ST_FORWARD = "Forwarding"
    ST_BLOCKED = "Blocked"
    ROLE_STATUS_MAP = { ROLE_ROOT: ST_FORWARD, ROLE_DESG: ST_FORWARD, ROLE_UNDESG: ST_BLOCKED }

    def __init__(self, num, cost):
        self.num = num
        self.cost = cost
        self.remote_port = None
        self.resetSTP()

    def resetSTP(self):
        self.best_bpdu = None
        self.role = Port.ROLE_UNDESG
        self.status = Port.ST_BLOCKED
        self.cost_to_root = None

    def setRemote(self, remote):
        self.remote_port = remote

    def sendBPDU(self, m):
        self.best_bpdu = self.best_bpdu.getBest(m) if self.best_bpdu else m
        self.remote_port.receiveBPDU(m)

    def receiveBPDU(self, m):
        self.best_bpdu = self.best_bpdu.getBest(m) if self.best_bpdu else m

    def setRole(self, role):
        self.role = role
        self.status = self.ROLE_STATUS_MAP[role]

# Bridge: Represents a network bridge with STP logic.
class Bridge(object):
    def __init__(self, label, id):
        self.label = label
        self.id = id
        self.ports = []

    def boot(self):
        self.best_bpdu = BPDU(self.id, 0, self.id, 0)
        self.root = True
        for p in self.ports:
            p.resetSTP()

    def processBPDUs(self):
        best = [BPDU(p.best_bpdu.root, p.best_bpdu.cost + p.cost, self.id, p.num)
                for p in self.ports if p.best_bpdu]
        best_bpdu = BPDU(self.id, 0, self.id, 0)
        root_port = None
        for b in best:
            if b.getBest(best_bpdu) == b:
                best_bpdu = b
                root_port = b.port
        self.root = best_bpdu.root == self.id

        if self.root:
            for p in self.ports:
                best_bpdu.port = p.num
                p.sendBPDU(best_bpdu)
                p.setRole(Port.ROLE_DESG)
        else:
            for p in self.ports:
                if best_bpdu.getBest(p.best_bpdu) == best_bpdu:
                    p.sendBPDU(best_bpdu)
                    p.setRole(Port.ROLE_DESG)
                    p.cost_to_root = None
                elif p.num == root_port:
                    p.cost_to_root = best_bpdu.cost
                    p.setRole(Port.ROLE_ROOT)
                else:
                    p.cost_to_root = None
                    p.setRole(Port.ROLE_UNDESG)

# --- Network class (Streamlit-ready) ---
# Network: Manages the network topology and connections.
class Network(object):
    COST_MAP = {10: 100, 100: 19, 1000: 4, 10000: 2}

    def __init__(self):
        self.bridges = {}

    def getBridge(self, label, id):
        if id in self.bridges:
            return self.bridges[id]
        br = Bridge(label, id)
        self.bridges[id] = br
        return br

    def getAllBridges(self):
        return self.bridges.values()

    def connect(self, br1, port1, br2, port2, speed):
        local = Port(port1, self.COST_MAP[speed])
        remote = Port(port2, self.COST_MAP[speed])
        local.setRemote(remote)
        remote.setRemote(local)
        br1.ports.append(local)
        br2.ports.append(remote)

# --- Load DOT topology ---
# buildNetworkFromDOT: Builds a network topology from a DOT file.
def buildNetworkFromDOT(dot_content):
    MG = nxd.nx_pydot.read_dot(io.StringIO(dot_content.decode("utf-8")))
    nodes = {}
    edges_data = MG.edges.data()
    nodes_data = MG.nodes.data()
    net = Network()
    for label, attr in nodes_data:
        mac = attr.get('mac', 'ff:ff:ff:ff:ff:ff').replace('"', '')
        pri = attr.get('priority', '32768')
        id = int(pri) * 2**48 + int(EUI(mac))
        nodes[label] = id
    for s, d, attr in edges_data:
        n = s.split(':')
        m = d.split(':')
        src_node = n[0]
        src_port = int(n[1])
        dst_node = m[0]
        dst_port = int(m[1])
        g1 = net.getBridge(src_node, nodes[src_node])
        g2 = net.getBridge(dst_node, nodes[dst_node])
        speed = int(attr['speed'])
        net.connect(g1, src_port, g2, dst_port, speed)
    return net

# --- Simulation logic ---
# simulate_stp: Simulates the Spanning Tree Protocol for a given number of steps.
def simulate_stp(net, steps):
    for br in net.getAllBridges():
        br.boot()
    for _ in range(steps):
        for br in net.getAllBridges():
            br.processBPDUs()

# render_results: Renders the simulation results in Streamlit.
def render_results(net):
    for br in net.getAllBridges():
        st.subheader(f"Bridge: {br.label}")
        root_text = "✅ Root Bridge" if br.root else f"Root ID: {hex(br.best_bpdu.root)}"
        st.write(f"ID: `{hex(br.id)}` - {root_text}")
        data = []
        for p in sorted(br.ports, key=lambda x: x.num):
            ctr = p.cost_to_root if p.cost_to_root else "-"
            data.append({
                "Port": p.num,
                "Role": p.role,
                "Status": p.status,
                "Cost": p.cost,
                "Cost-to-Root": ctr
            })
        st.table(data)

# --- Streamlit UI ---
# Main Streamlit application logic for STP simulation.
# Handles file upload, simulation steps, and result rendering.
st.title("🕸️ Spanning Tree Protocol (STP) Simulator")
st.divider()
st.write("Upload a DOT file describing the network topology and simulate STP behavior.")

dot_file = st.file_uploader("📂 Upload a .dot file", type=["dot"])
steps = st.slider("🌀 Number of simulation steps", 1, 20, 5)

if dot_file:
    try:
        dot_content = dot_file.read().decode("utf-8")
        
        st.toast(f"The DOT file '{dot_file.name}' has been successfully loaded.", icon="✅")

        st.divider()
        st.subheader("🔍 Network Topology (DOT format)")
        st.graphviz_chart(dot_content)
        
        st.divider()
        st.subheader("🔄 Simulation Results")
        net = buildNetworkFromDOT(dot_content.encode("utf-8"))
        simulate_stp(net, steps)
        render_results(net)
        
        st.divider()
        st.subheader("📜 Source Code")
        st.code(dot_content, language="dot")
    except Exception as e:
        st.error(f"❌ Error: {e}")
