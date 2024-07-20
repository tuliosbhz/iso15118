import json
import logging
import time
from builtins import Exception

from iso15118.shared.iexi_codec import IEXICodec
from iso15118.shared.settings import JAR_FILE_PATH
from py4j.java_gateway import JavaGateway, GatewayParameters, Py4JNetworkError, launch_gateway

logger = logging.getLogger(__name__)

def compare_messages(json_to_encode, decoded_json):
    json_obj = json.loads(json_to_encode)
    decoded_json_obj = json.loads(decoded_json)
    return sorted(json_obj.items()) == sorted(decoded_json_obj.items())

class ExificientEXICodec(IEXICodec):
    def __init__(self):
        logging.getLogger("py4j").setLevel(logging.CRITICAL)
        self.gateway = self.create_gateway()
        self.exi_codec = self.gateway.jvm.com.siemens.ct.exi.main.cmd.EXICodec()

    def create_gateway(self):
        port = launch_gateway(
            classpath=JAR_FILE_PATH,
            die_on_exit=True,
            javaopts=["--add-opens", "java.base/java.lang=ALL-UNNAMED"]
        )
        return JavaGateway(gateway_parameters=GatewayParameters(port=port))

    def reset_gateway(self):
        try:
            self.gateway.shutdown()
        except Exception as e:
            logger.error(f"Failed to shutdown Java gateway: {e}")
        finally:
            self.gateway = self.create_gateway()
            self.exi_codec = self.gateway.jvm.com.siemens.ct.exi.main.cmd.EXICodec()
    
    def stop_gateway(self):
        try:
            self.gateway.shutdown()
        except Exception as e:
            logger.error(f"Failed to shutdown Java gateway: {e}")
        finally:
            return

    def encode(self, message: str, namespace: str) -> bytes:
        """
        Calls the Exificient EXI implementation to encode input json.
        Returns a byte[] for the input message if conversion was successful.
        """
        try:
            exi = self.exi_codec.encode(message, namespace)
            if exi is None:
                raise Exception(self.exi_codec.get_last_encoding_error())
            return exi
        except Py4JNetworkError:
            logger.error("Py4JNetworkError: Resetting the gateway.")
            self.reset_gateway()
            exi = self.exi_codec.encode(message, namespace)
            if exi is None:
                raise Exception(self.exi_codec.get_last_encoding_error())
            return exi

    def decode(self, stream: bytes, namespace: str) -> str:
        """
        Calls the EXIficient EXI implementation to decode the input EXI stream.
        Returns a JSON representation of the input EXI stream if the conversion
        was successful.
        """
        try:
            decoded_message = self.exi_codec.decode(stream, namespace)
            if decoded_message is None:
                raise Exception(self.exi_codec.get_last_decoding_error())
            return decoded_message
        except Py4JNetworkError:
            logger.error("Py4JNetworkError: Resetting the gateway.")
            self.reset_gateway()
            decoded_message = self.exi_codec.decode(stream, namespace)
            if decoded_message is None:
                raise Exception(self.exi_codec.get_last_decoding_error())
            return decoded_message

    def get_version(self) -> str:
        """
        Returns the version of the Exificient codec
        """
        return self.exi_codec.get_version()
