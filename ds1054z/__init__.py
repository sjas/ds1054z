"""
The class :py:mod:`ds1054z.DS1054Z` - Easy communication with your scope
========================================================================
"""

import logging
import re
import time
import sys
import os

import vxi11

logger = logging.getLogger(__name__)

try:
    clock = time.perf_counter
except:
    clock = time.time

class DS1054Z(vxi11.Instrument):
    """
    This class represents the oscilloscope.
    """

    IDN_PATTERN = r'^RIGOL TECHNOLOGIES,DS1\d\d\dZ,'
    ENCODING = 'utf-8'
    H_GRID = 12
    DISPLAY_DATA_BYTES = 1152068

    def __init__(self, host, *args, **kwargs):
        self.start = clock()
        super(DS1054Z, self).__init__(host, *args, **kwargs)
        idn = self.idn
        assert re.match(self.IDN_PATTERN, idn)
        idn = idn.split(',')
        self.vendor = idn[0]
        self.product = idn[1]
        self.serial = idn[2]
        self.firmware = idn[3]

    def clock(self):
        return clock() - self.start

    def log_timing(self, msg):
        logger.info('{0:.3f} - {1}'.format(self.clock(), msg))

    def write_raw(self, cmd, *args, **kwargs):
        self.log_timing('starting write')
        logger.debug('sending: ' + repr(cmd))
        super(DS1054Z, self).write_raw(cmd, *args, **kwargs)
        self.log_timing('finishing write')

    def read_raw(self, *args, **kwargs):
        self.log_timing('starting read')
        data = super(DS1054Z, self).read_raw(*args, **kwargs)
        self.log_timing('finished reading {} bytes'.format(len(data)))
        if len(data) > 200:
            logger.debug('received a long answer: {} ... {}'.format(format_hex(data[0:10]), format_hex(data[-10:])))
        else:
            logger.debug('received: ' + repr(data))
        return data

    def query(self, message, *args, **kwargs):
        """
        Write a message to the scope and read back the answer.
        See vxi11.Instrument.ask() for optional parameters.
        """
        return self.ask(message, *args, **kwargs)

    def query_raw(self, message, *args, **kwargs):
        """
        Write a message to the scope and read a (binary) answer.

        This is the slightly modified version of vxi11.Instrument.ask_raw().
        It takes a command message string and returns the answer as bytes.
        """
        data = message.encode(self.ENCODING)
        return self.ask_raw(data, *args, **kwargs)

    def get_waveform(self, channel, mode='NORMal'):
        """
        Get the waveform data for a specific channel

        :param channel: The channel name (like CHAN1, ...). Alternatively specify the channel by its number (as integer).
        :type channel: int or str
        :param str mode: can be NORMal, MAX, or RAW
        :return: The waveform data
        :rtype: bytes
        """
        if type(channel) == int: channel = 'CHAN' + str(channel)
        self.write(":WAVeform:SOURce " + channel)
        self.write(":WAVeform:FORMat BYTE")
        self.write(":WAVeform:MODE " + mode)
        self.query(":WAVeform:STARt?")
        self.query(":WAVeform:STOP?")
        buff = self.query_raw(":WAVeform:DATA?")
        return DS1054Z._clean_tmc_header(buff)

    @staticmethod
    def _clean_tmc_header(tmc_data):
        if sys.version_info >= (3, 0):
            n_header_bytes = int(chr(tmc_data[1]))+2
        else:
            n_header_bytes = int(tmc_data[1])+2
        n_data_bytes = int(tmc_data[2:n_header_bytes].decode('ascii'))
        return tmc_data[n_header_bytes:n_header_bytes + n_data_bytes]

    @property
    def idn(self):
        """
        The ``*IDN?`` string of the device.
        Will be fetched every time you access this property.
        """
        return self.query("*IDN?")

    def stop(self):
        """ Stop acquisition """
        self.write(":STOP")

    def run(self):
        """ Start acquisition """
        self.write(":RUN")

    def single(self):
        """ Set the oscilloscope to the single trigger mode. """
        self.write(":SINGle")

    def tforce(self):
        """ Generate a trigger signal forcefully. """
        self.write(":TFORce")

    @property
    def memory_depth(self):
        """
        The current memory depth of the oscilloscope as float.
        This property will be updated every time you access it.
        """
        mdep = self.query(":ACQuire:MDEPth?")
        if mdep == "AUTO":
            srate = self.query(":ACQuire:SRATe?")
            scal = self.query(":TIMebase:MAIN:SCALe?")
            mdep = self.H_GRID * float(scal) * float(srate)
        return float(mdep)

    @property
    def display_data(self):
        """
        The bitmap bytes of the current screen content.
        This property will be updated every time you access it.
        """
        self.write(":DISPlay:DATA?")
        logger.info("Receiving screen capture...")
        buff = self.read_raw(self.DISPLAY_DATA_BYTES)
        logger.info("read {} bytes in .display_data".format(len(buff)))
        if len(buff) != self.DISPLAY_DATA_BYTES:
            raise NameError("display_data: didn't receive the right number of bytes")
        return DS1054Z._clean_tmc_header(buff)

    @property
    def displayed_channels(self):
        """
        The list of channels currently displayed on the scope.
        This property will be updated every time you access it.
        """
        channel_list = []
        for channel in ["CHAN1", "CHAN2", "CHAN3", "CHAN4", "MATH"]:
            if self.query(channel + ":DISPlay?") == '1':
                channel_list.append(channel)
        return channel_list

    # return maximum achieved stop point, or 0 for wrong input parameters
    # if achieved == requested, then set the start and stop waveform as n1_d and n2_d
    def is_waveform_from_to(self, n1_d, n2_d):
        # read current
        # WAVeform:STARt
        n1_c = float(self.query(":WAVeform:STARt?"))

        # WAVeform:STOP
        n2_c = float(self.query(":WAVeform:STOP?"))

        if (n1_d > n2_d) or (n1_d < 1) or (n2_d < 1):
            # wrong parameters
            return 0

        elif n2_d < n1_c:
            # first set n1_d then set n2_d
            self.write(":WAVeform:STARt " + str(n1_d))
            time.sleep(0.3)
            self.write(":WAVeform:STOP " + str(n2_d))
            time.sleep(0.3)

        else:
            # first set n2_d then set n1_d
            self.write(":WAVeform:STOP " + str(n2_d))
            time.sleep(0.3)
            self.write(":WAVeform:STARt " + str(n1_d))
            time.sleep(0.3)

        # read achieved n2
        n2_a = float(self.query(":WAVeform:STOP?"))

        if n2_a < n2_d:
            # restore n1_c, n2_c
            self.is_waveform_from_to(n1_c, n2_c)

        return n2_a

    def get_csv(self):
        # self.stop()
        channel_list = self.displayed_channels
        depth = self.memory_depth
        csv_buff = ""
        for channel in channel_list:
            self.write(":WAVeform:SOURce " + channel)
            time.sleep(0.2)
            self.write(":WAVeform:FORMat ASC")
            time.sleep(0.2)
            # Maximum - only displayed data when osc. in RUN mode, or full memory data when STOPed
            self.write(":WAVeform:MODE MAX")
            time.sleep(0.2)
            # Get all data available
            buff = ""
            # max_chunk is dependent of the wav:mode and the oscilloscope type
            # if you get on the oscilloscope screen the error message
            # "Memory lack in waveform reading!", then decrease max_chunk value
            max_chunk = 100000.0  # tested for DS1104Z
            if max_chunk > depth:
                max_chunk = depth
            n1 = 1.0
            n2 = max_chunk
            data_available = True
            while data_available:
                display_n1 = n1
                stop_point = self.is_waveform_from_to(n1, n2)
                if stop_point == 0:
                    data_available = False
                    logger.error("Stop data point index lower then start data point index")
                    raise NameError("Stop data point index lower then start data point index")
                elif stop_point < n1:
                    break
                elif stop_point < n2:
                    n2 = stop_point
                    self.is_waveform_from_to(n1, n2)
                    data_available = False
                else:
                    data_available = True
                    n1 = n2 + 1
                    n2 += max_chunk
                self.write(":WAVeform:DATA?")
                logger.info("Data from channel " + str(channel) + ", points " +\
                      str(int(display_n1)) + "-" + str(int(stop_point)) + ": Receiving...")
                buff_chunks = self.read_raw(int(max_chunk))
                buff_chunks = buff_chunks.decode('ascii')
                # Strip TMC Blockheader and terminator bytes
                buff += DS1054Z._clean_tmc_header(buff_chunks) + ","
            buff = buff[:-1]
            buff_list = buff.split(",")
            buff_rows = len(buff_list)
            csv_buff_list = csv_buff.split(os.linesep)
            csv_rows = len(csv_buff_list)
            current_row = 0
            if csv_buff == "":
                csv_first_column = True
                csv_buff = str(channel) + os.linesep
            else:
                csv_first_column = False
                csv_buff = str(csv_buff_list[current_row]) + "," + str(channel) + os.linesep
            for point in buff_list:
                current_row += 1
                if csv_first_column:
                    csv_buff += str(point) + os.linesep
                else:
                    if current_row < csv_rows:
                        csv_buff += str(csv_buff_list[current_row]) + "," + str(point) + os.linesep
                    else:
                        csv_buff += "," + str(point) + os.linesep
        return csv_buff


def format_hex(byte_str):
    if sys.version_info >= (3, 0):
        return ''.join( [ "%02X " % x  for x in byte_str ] ).strip()
    else:
        return ''.join( [ "%02X " % ord(x)  for x in byte_str ] ).strip()
