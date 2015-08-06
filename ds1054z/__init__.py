
import vxi11

class DS1054Z(vxi11.Instrument):

    ENCODING = 'utf-8'
    H_GRID = 12

    def query(self, *args, **kwargs):
        return self.ask(*args, **kwargs)

    def query_raw(self, cmd, *args, **kwargs):
        cmd = cmd.encode(self.ENCODING)
        return self.ask_raw(cmd, *args, **kwargs)

    @property
    def memory_depth(self):
        # ACQuire:MDEPth
        mdep = self.query("ACQ:MDEP?")

        if mdep == "AUTO":
            # ACQuire:SRATe
            srate = self.query("ACQ:SRAT?")

            # TIMebase[:MAIN]:SCALe
            scal = self.query("TIM:SCAL?")

            mdep = self.H_GRID * float(scal) * float(srate)

        return float(mdep)
