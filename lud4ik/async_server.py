from work.protocol import feed
from work.cmdargs import get_cmd_args
from work.utils import get_random_hash
from work.loop import EventLoop
from work.layer import Factory, Protocol


if __name__ == '__main__':
    args = get_cmd_args()
    event_loop = EventLoop()
    event_loop.run()