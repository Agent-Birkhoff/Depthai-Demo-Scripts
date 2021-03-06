import time

import cv2
import depthai as dai
import numpy as np

blob = dai.OpenVINO.Blob("./models/DDRNet/640_360.blob")  # TODO MODEL PATH
for name, tensorInfo in blob.networkInputs.items():
    print(name, tensorInfo.dims)
INPUT_SHAPE = blob.networkInputs["0"].dims[:2]


class FPSHandler:
    def __init__(self):
        self.timestamp = time.time()
        self.start = time.time()
        self.frame_cnt = 0

    def next_iter(self):
        self.timestamp = time.time()
        self.frame_cnt += 1

    def fps(self):
        return self.frame_cnt / (self.timestamp - self.start)


# Start defining a pipeline
pipeline = dai.Pipeline()

cam = pipeline.create(dai.node.ColorCamera)
cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
cam.setIspScale((1, 3), (1, 3))  # TODO RGB->640x360
cam.setBoardSocket(dai.CameraBoardSocket.RGB)
cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.RGB)
cam.setPreviewSize(*INPUT_SHAPE)
cam.setInterleaved(False)

# Define a neural network that will make predictions based on the source frames
detection_nn = pipeline.create(dai.node.NeuralNetwork)
detection_nn.setBlob(blob)
detection_nn.input.setBlocking(False)
detection_nn.setNumInferenceThreads(2)
cam.preview.link(detection_nn.input)

# NN output linked to XLinkOut
xout_nn = pipeline.create(dai.node.XLinkOut)
xout_nn.setStreamName("nn")
detection_nn.out.link(xout_nn.input)
xout_img = pipeline.create(dai.node.XLinkOut)
xout_img.setStreamName("img")
detection_nn.passthrough.link(xout_img.input)

# Pipeline is defined, now we can connect to the device
with dai.Device() as device:
    device.startPipeline(pipeline)
    q_nn = device.getOutputQueue(name="nn", maxSize=4, blocking=False)  # type: ignore
    q_img = device.getOutputQueue(name="img", maxSize=4, blocking=False)  # type: ignore
    fps = FPSHandler()
    while True:
        msgs = q_nn.get()
        img = q_img.get().getCvFrame()
        fps.next_iter()

        # get layer1 data
        layer1 = msgs.getFirstLayerFp16()
        # reshape to numpy array
        frame = np.asarray(layer1).reshape(INPUT_SHAPE[1], INPUT_SHAPE[0]) > 0.5
        frame = frame.astype(np.uint8) * 255

        frame = np.concatenate((img, np.stack((frame,) * 3, axis=2)), axis=0)

        cv2.putText(
            frame,
            "Fps: {:.2f}".format(fps.fps()),
            (2, frame.shape[0] - 4),
            cv2.FONT_HERSHEY_TRIPLEX,
            0.4,
            color=(255, 255, 255),
        )
        cv2.imshow("Frame", frame)

        if cv2.waitKey(1) == ord("q"):
            break
