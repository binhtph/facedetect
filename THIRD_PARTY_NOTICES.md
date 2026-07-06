# Third-Party Notices

This file identifies the primary third-party components used by IRIS. Copyright and license files shipped inside installed packages and Docker image layers remain applicable. The complete dependency lists are in `package-lock.json` and `backend/requirements.txt`.

## InsightFace

- Project: [deepinsight/insightface](https://github.com/deepinsight/insightface)
- Authors: InsightFace Contributors
- Code license: MIT; see the [official package notice](https://github.com/deepinsight/insightface/tree/master/python-package#license)
- Python package: `insightface==1.0.1`

The InsightFace Python source code permits academic and commercial use under the MIT License. InsightFace states separately that pretrained models it provides, whether downloaded automatically or manually, are available for non-commercial research purposes only. IRIS downloads those model packs from InsightFace's official release and does not claim ownership or grant additional model rights.

### InsightFace MIT notice

Copyright (c) InsightFace Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Runtime and computer vision

| Component                                                            | Copyright/project                   | License                                                                                       |
| -------------------------------------------------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------- |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime)             | Microsoft Corporation               | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE)                             |
| [OpenCV](https://github.com/opencv/opencv)                           | OpenCV contributors                 | [Apache-2.0](https://github.com/opencv/opencv/blob/4.x/LICENSE)                               |
| [FastAPI](https://github.com/fastapi/fastapi)                        | FastAPI contributors                | [MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE)                                 |
| [Paho MQTT Python](https://github.com/eclipse-paho/paho.mqtt.python) | Eclipse Foundation and contributors | [EPL-2.0 / EDL-1.0](https://github.com/eclipse-paho/paho.mqtt.python/blob/master/LICENSE.txt) |

## Web application

| Component                                             | Copyright/project                   | License                                                     |
| ----------------------------------------------------- | ----------------------------------- | ----------------------------------------------------------- |
| [React](https://github.com/facebook/react)            | Meta Platforms, Inc. and affiliates | [MIT](https://github.com/facebook/react/blob/main/LICENSE)  |
| [TanStack Router](https://github.com/TanStack/router) | TanStack contributors               | [MIT](https://github.com/TanStack/router/blob/main/LICENSE) |
| [Vite](https://github.com/vitejs/vite)                | Vite contributors                   | [MIT](https://github.com/vitejs/vite/blob/main/LICENSE)     |

This notice is informational and does not replace the license text included with each dependency.
