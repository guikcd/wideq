import argparse
import logging

from wideq import server

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='REST API for the LG SmartThinQ wideq Lib.'
    )

    parser.add_argument(
        '--port', '-p', type=int,
        help='port for server (default: 5025)',
        default=5025
    )
    parser.add_argument(
        '--verbose', '-v',
        help='verbose mode to help debugging',
        action='store_true', default=False
    )

    args = parser.parse_args()

    logging.basicConfig(filename='lgthinq.log', format='%(asctime)s:%(levelname)s:%(message)s',
        level= logging.DEBUG if args.verbose else logging.INFO)
    
    api = server.create_app( debug= args.verbose)
    api.run(host="0.0.0.0", port=args.port, debug=args.verbose)
