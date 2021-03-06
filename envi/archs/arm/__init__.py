
"""
The initial arm module.
"""

import envi

from envi.archs.arm.regs import *
from envi.archs.arm.disasm import *
from envi.archs.arm.armdisasm import *
from envi.archs.arm.thumbdisasm import *

class ArmModule(envi.ArchitectureModule):

    def __init__(self):
        envi.ArchitectureModule.__init__(self, "armv6", maxinst=4)
        self._arch_reg = self.archGetRegCtx()
        self._arch_dis = ArmDisasm()

    def setModeThumb(self):
        self._arch_dis.setMode(MODE_THUMB)

    def archGetRegCtx(self):
        return ArmRegisterContext()

    def archGetBreakInstr(self):
        raise Exception ("weird... what are you trying to do here?  ARM has a complex breakpoint instruction")
        return 
 
    def getPointerSize(self):
        return 4

    def pointerString(self, va):
        return "0x%.8x" % va

    def makeOpcode(self, bytes, offset=0, va=0):
        """
        Parse a sequence of bytes out into an envi.Opcode instance.
        """
        return self._arch_dis.disasm(bytes, offset, va)

    def getEmulator(self):
        return ArmEmulator()

from envi.archs.arm.emu import *
