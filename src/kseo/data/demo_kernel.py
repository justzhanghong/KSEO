"""CPU 示例中的可修改源码；不代表真实 GPU Kernel。"""

KERNEL_SCALE = 1.0
SCHEDULER_SCALE = 1.0


def kernel_value(x):
    return x * x + 1
