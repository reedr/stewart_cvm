"""Stewart CVM Device."""

import asyncio
import logging
from operator import itemgetter
import re
import time

from homeassistant.core import HomeAssistant, callback

from .const import (
    CVM_CONNECT_TIMEOUT,
    CVM_CALIBRATE_TIMEOUT,
    CVM_LOGIN_TIMEOUT,
    CVM_MIN_COMMAND_INTERVAL,
    CVM_PORT,
)

_LOGGER = logging.getLogger(__name__)

MIN_COVER_POSITION = 0 # narrowest
MAX_COVER_POSITION = 100 # widest

class CVMDevice:
    """Represents a single CVM device."""

    def __init__(
        self, hass: HomeAssistant, host: str, username: str, password: str, presets_aspect: str, presets_position: str
    ) -> None:
        """Set up class."""

        self._hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._device_id = f"CVM:{host}"
        self._reader: asyncio.StreamReader
        self._writer: asyncio.StreamWriter
        self._online = False
        self._callback = None
        pat = r'[^!#]*([!#])1\.1\.(\d)\.MOTOR(\.[^=]+)?=([?.0-9A-Z]+)'
        self._match_re = re.compile(pat.encode('ascii'))
        self._aspect_ratios = []
        motor_positions = [float(p) for p in presets_position.split(",")]
        self.set_aspect_ratios(presets_aspect, motor_positions)
        self._data = {
                        "position": None,
                        "motor_status": "STOP",
                        "motor_position": None,
                        "aspect_ratios": self._aspect_ratios,
                        "screen_aspect_ratio": None,
                        "screen_aspect_ratio_string": None,
                        "screen_preset": None
                      }
        self._data["aspect_ratios"] = self._aspect_ratios
        self._init_event = asyncio.Event()
        self._calibrate_event = asyncio.Event()
        self._command_block_event = asyncio.Event()
        self._command_block_event.set()
        self._last_command_sent = None
        self._is_moving = False
        self._listener = None

    def set_aspect_ratios(self, presets_aspect: str, motor_positions: list[float]) -> None:
        self._aspect_ratios = sorted([{"name": ar,
                                       "value": float(ar),
                                       "preset": i+1,
                                       "motor_position": motor_positions[i],
                                       "cover_position": int((max(motor_positions) - motor_positions[i])
                                                              * MAX_COVER_POSITION / max(motor_positions))}
                                     for i, ar in enumerate(presets_aspect.split(","))],
                                     key=itemgetter("value"))
        for ar in self._aspect_ratios:
            _LOGGER.info("aspect ratio: '%s' => %.2f cover=%d motor=%.2f preset=%d", ar["name"], ar["value"], ar["cover_position"], ar["motor_position"], ar["preset"])

    @property
    def device_id(self) -> str:
        """Use the mac."""
        return self._device_id

    @property
    def online(self) -> bool:
        """Return status."""
        return self._online

    @property
    def data(self) -> dict:
        """Dev data."""
        return self._data

    @property
    def aspect_ratios(self) -> list[str]:
        """Strings for aspect ratios."""
        return [ar["name"] for ar in self._aspect_ratios]

    def cover_position_to_aspect(self, position: int) -> dict:
        """Find aspect just larger than position."""
        if position <= MIN_COVER_POSITION:
            return self._aspect_ratios[0]
        if position >= MAX_COVER_POSITION:
            return self._aspect_ratios[-1]
        for ar in self._aspect_ratios:
            if position <= ar["cover_position"]:
                return ar
        return self._aspect_ratios[-1]

    def motor_position_to_aspect(self, position: float) -> dict:
        """Find aspect just larger than position."""
        close_i = 0
        close_diff = 100
        for i, ar in enumerate(self._aspect_ratios):
            diff = abs(position - ar["motor_position"])
            if diff < close_diff:
                close_diff = diff
                close_i = i
        return self._aspect_ratios[close_i]

    def aspect_ratio_lookup(self, aspect: str) -> dict:
        """Lookup the aspect."""
        for ar in self._aspect_ratios:
            if ar["name"] == aspect:
                return ar
        return None


    async def open_connection(self, test: bool=False) -> bool:
        """Establish a connection."""
        if self.online and not self._writer.is_closing():
            return True

        try:
            _LOGGER.debug("Establish new connection")
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, CVM_PORT),
                timeout=CVM_CONNECT_TIMEOUT
            )
            await asyncio.wait_for(
                self._reader.readuntil(b"User:"),
                timeout=CVM_LOGIN_TIMEOUT
            )
            self._writer.write(self._username.encode('ascii') + b"\r")
            await asyncio.wait_for(
                self._reader.readuntil(b"Password:"),
                timeout=CVM_LOGIN_TIMEOUT
            )
            self._writer.write(self._password.encode('ascii') + b"\r")
            await asyncio.wait_for(
                self._reader.readuntil(b"Connected:"),
                timeout=CVM_LOGIN_TIMEOUT
            )
            if test:
                self._writer.close()
            else:
                self._online = True
                self._listener = asyncio.create_task(self.listener())

        except (TimeoutError, OSError, asyncio.IncompleteReadError) as err:
            self._online = False
            _LOGGER.error("Connect sequence error %s", err)
            raise ConnectionError("Connect sequence error") from err

        return True

    async def test_connection(self) -> bool:
        """Test a connect."""
        return await self.open_connection(test=True)

    async def maybe_delay_command(self, wait: bool = True) -> None:
        """Wait if it's been too soon."""
        if self._last_command_sent is not None:
            dt = time.time() - self._last_command_sent
            if dt < CVM_MIN_COMMAND_INTERVAL:
                if wait:
                    await asyncio.sleep(CVM_MIN_COMMAND_INTERVAL - dt)
                else:
                    return False
        return True

    async def send_command(self, command: str) -> bool:
        """Make an API call."""
        if await self.open_connection():
            cmd = command.encode('ascii') + b"\r\n"
            _LOGGER.debug("-> %s", str(cmd))
            self._writer.write(cmd)
            self._last_command_sent = time.time()
            return True
        return False

    async def send_query_position(self) -> bool:
        """Query."""
        if await self.maybe_delay_command(wait=False):
            return await self.send_command("#1.1.1.MOTOR.POSITION=?")
        return False

    async def send_recall(self, preset: int) -> bool:
        """Recall a preset."""
        await self.maybe_delay_command()
        return await self.send_command(f"#1.1.0.MOTOR=RECALL,{preset};")

    async def set_aspect_ratio(self, aspect: str) -> bool:
        """Set mask from aspect ratio."""
        ar = self.aspect_ratio_lookup(aspect)
        _LOGGER.debug("set_aspect_ratio: %s => %.2f cover=%d motor=%.2f preset=%d", aspect, ar["value"], ar["cover_position"], ar["motor_position"], ar["preset"])
        return await self.send_recall(ar["preset"])

    async def set_position(self, position: int) -> bool:
        """Setit."""
        ar = self.cover_position_to_aspect(position)
        return await self.send_recall(ar["preset"])

    async def open_mask(self) -> bool:
        """Open wide."""
        return await self.send_command("#1.1.0.MOTOR=RETRACT;")

    async def close_mask(self) -> bool:
        """Narrow bridge."""
        return await self.set_position(0)

    async def stop_mask(self) -> bool:
        """Stop moving."""
        return await self.send_command("#1.1.0.MOTOR=STOP;")

    async def async_recalibrate(self, aspect_ratios_conf: list[str]) -> str | None:
        """Calibrate."""
        _LOGGER.info("Calibrating")
        aspect_ratios = sorted([{"name": ar, "value": float(ar), "preset": i+1}
                                 for i, ar in enumerate(aspect_ratios_conf.split(","))],
                                   key=itemgetter("value"))
        motor_positions = [0] * len(aspect_ratios)
        motor_positions_conf = None
        try:
            for i, ar in enumerate(aspect_ratios):
                self._calibrate_event.clear()
                await self.send_recall(ar["preset"])
                await asyncio.wait_for(
                    self._calibrate_event.wait(),
                    timeout=CVM_CALIBRATE_TIMEOUT
                )
                await asyncio.sleep(5.0)
                _LOGGER.debug("Calibrated %s preset=%d motor=%.2f", ar["name"], ar["preset"], self._data["motor_position"])
                motor_positions[i] = self._data["motor_position"]
            motor_positions_conf = ",".join([str(p) for p in motor_positions])
            self.set_aspect_ratios(aspect_ratios_conf, motor_positions)
            _LOGGER.info("Calibration complete")
        except TimeoutError:
            _LOGGER.error("Calibration timeout")
        except Exception as err:
            _LOGGER.error("Calibration error: %s", err)
        return motor_positions_conf

    async def async_init(self, data_callback: callback) -> dict:
        """Query position and wait for response."""
        self._callback = data_callback
        await self.send_query_position()
        await asyncio.wait_for(
            self._init_event.wait(),
            timeout=CVM_LOGIN_TIMEOUT
        )
        return self._data

    async def listener(self) -> None:
        """Listen for status updates from device."""

        while True:
            try:
                line = await self._reader.readuntil(b"\n")

                _LOGGER.debug("<- %s", str(line))
                if line == b"\n":
                    continue

                match = self._match_re.match(line)
                if match is None:
                    _LOGGER.error("Unexpected screen response: %s", line)
                    continue

                #_LOGGER.debug(str(match.group(1, 2, 3, 4)))
                if match.group(1) == b'#' and match.group(4) == b"RECALL":
                    _LOGGER.debug("screen moving")
                    self._is_moving = True
                elif match.group(1) == b'!':
                    if match.group(3) == b".POSITION" and match.group(2) == b"1":
                        motor_position = float(match.group(4))
                        if motor_position == self._data["motor_position"]:
                            self._is_moving = False
                            if not self._calibrate_event.is_set():
                                _LOGGER.debug("Position not changed, assuming calibration complete")
                                self._calibrate_event.set()
                        else:
                            ar = self.motor_position_to_aspect(motor_position)
                            _LOGGER.debug("Mask position: motor=%.2f position=%d aspect=%s preset=%d",
                                          motor_position, ar["cover_position"], ar["name"], ar["preset"])
                            self._data["cover_position"] = ar["cover_position"]
                            self._data["motor_position"] = motor_position
                            self._data["screen_aspect_ratio"] = ar["value"]
                            self._data["screen_aspect_ratio_string"] = ar["name"]
                            self._data["screen_preset"] = ar["preset"]
                            if not self._init_event.is_set():
                                self._init_event.set()
                            if self._callback is not None:
                                self._callback(self._data)
                    elif match.group(3) == b".STATUS":
                        status = str(match.group(4), encoding='ascii')
                        if status == "STOP":
                            _LOGGER.debug("Motor %s stopped", str(match.group(2), encoding='ascii'))
                            self._is_moving = False
                            self._calibrate_event.set()
                        if status != self._data["motor_status"]:
                            _LOGGER.debug("Mask status: %s", status)
                            self._data["motor_status"] = status
                            if self._callback is not None:
                                self._callback(self._data)

            except (asyncio.IncompleteReadError, ConnectionResetError) as err:
                _LOGGER.error("Connection lost during read: %s", err)
                self._writer.close()
                self._online = False
                break

            except Exception as err:
                _LOGGER.error("Unexpected read error: %s", err)
                self._writer.close()
                self._online = False
                break