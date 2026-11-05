#!/usr/bin/python4
from bcc import BPF
from time import sleep

program = """
int hello_world(void *ctx){
    u64 uid;

    uid = bpf_get_current_uid_gid() & 0xFFFFFFFF;
    if (uid == 0)
        bpf_trace_printk("id: %d\\n", uid);
    return 0;
}
"""

b = BPF(text=program)
clone = b.get_syscall_fnname("clone")
b.attach_kprobe(event=clone, fn_name="hello_world")
b.trace_print()