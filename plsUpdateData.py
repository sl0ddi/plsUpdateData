import argparse
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


DATAPATH = "plsData"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def required_length_splitted(nmin, nmax, separator):
    class RequiredLength(argparse.Action):
        def __call__(self, parser, args, values, option_string=None):
            value = values[0].split(".")
            if not nmin<=len(value)<=nmax:
                msg='argument "{f}" requires between {nmin} and {nmax} arguments separated by "{separator}"'.format(
                    f=self.dest,nmin=nmin,nmax=nmax,separator=separator)
                raise argparse.ArgumentTypeError(msg)
            setattr(args, self.dest, value)
    return RequiredLength


def read_args():
    parser = argparse.ArgumentParser(
        prog='plsUpdateData',
        description='Update plutus data graphs from commandline',
    )
    parser.add_argument('-u', '--update', help="Should graph update from remote. When used, defaults to 'force'd update, otherwise defaults to 'auto' which checks for updates every 10 minutes.",
                    default='auto',
                    const='force',
                    nargs='?',
                    choices=['d', 'disable', 'f', 'force', 'a', 'auto'],)
    parser.add_argument('-l', '--list', help="Lists all token/graph/chain combos.", action='store_true')
    parser.add_argument('-li', '--list-info', help="Lists all token/graph/chain combos with more information.", action='store_true')
    parser.add_argument('-s', '--select', help="Selects a graph with identifier or index", nargs=1, type=str,
                        action=required_length_splitted(1, 3, "."), metavar=("TOKEN.GRAPH?.CHAIN?=global"))
    parser.add_argument('-a', '--add', help=f'Add datapoint to graph. Accepts number, timestamp ({TIME_FORMAT.replace("%","0")}) or "NOW".', nargs=2, metavar=("X", "Y"))
    parser.add_argument('-t', '--to', help="define index to add datapoint to.", nargs=1, type=int, metavar="INDEX")
    parser.add_argument('-r', '--remove', help="Remove datapoint from index", nargs=1, type=int, metavar="INDEX")
    parser.add_argument('-d', '--data', help="Show selected graph data.", action='store_true')
    parser.add_argument('-p', '--plot', help="plot selected graph data.", action='store_true')
    parser.add_argument('--commit', help=f'Commit changes.', action='store_true')
    parser.add_argument('--push', help=f'(Commit if necessary and) Push changes.', action='store_true')

    return parser.parse_args(args=None if sys.argv[1:] else ['--help'])


def read_status():
    path = os.path.dirname(os.path.realpath(__file__))
    if os.path.exists(path+"/pUD_status.json"):
        with open(path+"/pUD_status.json") as f:
            status = json.load(f)
    else:
        status = {
            "selected": "",
            "action_history": [{'type': 'init', 'success': True, 'timestamp': time.time()}],
            "last_update": 0
        }
    if not 'selected' in status:
        status['selected'] = ''
    if not 'action_history' in status:
        status['action_history'] = []
    if 'last_action' in status:
        del status['last_action']

    status['datapath'] = path + "/" + DATAPATH
    save_status(status)
    return status

def save_status(status):
    path = os.path.dirname(os.path.realpath(__file__))
    with open(path+"/pUD_status.json", 'w') as f:
        f.write(json.dumps(status, indent=2))

def get_graphs(dp):
    files = os.listdir(dp)
    graphs = {}
    for file in files:
        if file.endswith(".json"):
            token = file.split(".")[0]
            with open(dp +"/"+file) as f:
                data = json.load(f)
            graphs[token] = data
    return graphs

def list_graphs(graphs, selection, info=False):
    graph_index = 0
    for t in graphs.keys():
        print(t)
        for g in graphs[t].keys():
            print("  - " + g)
            for c in graphs[t][g].keys():
                mark = " -"
                if selection == f'{t}.{g}.{c}':
                    mark = "->"
                infos = ''
                if info:
                    infos = f'   |   Points:{len(graphs[t][g][c]): >4}'
                    if len(graphs[t][g][c]) > 0:
                        infos += f'   |   Last:  x: {str(graphs[t][g][c][-1][0]): >20}  y: {str(graphs[t][g][c][-1][1]): >20}'
                print(f'     {mark} {"["+str(graph_index)+"]": <4} {c: <20}{infos}')


                graph_index += 1
    return True


def graph_by_index(graphs, i):
    graph_index = 0
    for t in graphs.keys():
        for g in graphs[t].keys():
            l = len(graphs[t][g].keys())
            if graph_index + l > i:
                return True, t, g, list(graphs[t][g].keys())[i - graph_index]
            graph_index += l
    return False, '', '', ''

def select_graph(graphs, selection, status):
    t = ""
    g = ""
    c = ""
    if len(selection) > 0:
        tlist = list(map(str.lower, graphs.keys()))
        stoken = selection[0].lower()
        if stoken in tlist:
            t = list(graphs.keys())[tlist.index(stoken)]
            if len(selection) > 1:
                glist = list(map(str.lower, graphs[t].keys()))
                sgraph = selection[1].lower()
                if sgraph in glist:
                    g = list(graphs[t].keys())[glist.index(sgraph)]
                else:
                    print(f'Token {t} has no graph {selection[1]}')
                    if len(graphs[t].keys()) > 0:
                        print(f'Please select a GRAPH from {graphs[t].keys()} by using {t}.GRAPH as identifier')
            elif len(graphs[t].keys()) == 1:
                g = list(graphs[t].keys())[0]
            else:
                print('Could not select graph by default value.')
                if len(graphs[t].keys()) > 1:
                    print(f'Please select a GRAPH from {graphs[t].keys()} by using {t}.GRAPH as identifier')
            if g != "":
                if len(selection) > 2:
                    clist = list(map(str.lower, graphs[t][g].keys()))
                    schain = selection[2].lower()
                    if schain in clist:
                        c = list(graphs[t][g].keys())[clist.index(schain)]
                    else:
                        print(f'Graph {t}.{g} has no chain {selection[0]}')
                        if len(graphs[t][g].keys()) > 0:
                            print(f'Please select a GRAPH from {graphs[t][g].keys()} by using {t}.{g}.CHAIN as identifier')
                elif len(graphs[t].keys()) == 1:
                    c = list(graphs[t][g].keys())[0]
                elif 'global' in graphs[t][g].keys():
                    c = 'global'
                else:
                    print('Could not select chain by default value.')
                    if len(graphs[t].keys()) >= 1:
                        print(f'Please select a CHAIN from {graphs[t][g].keys()} by using {t}.{g}.CHAIN as identifier')
                if c != "":
                    status['selected'] = f'{t}.{g}.{c}'
                    set_status(status, "selected", f'{t}.{g}.{c}')
                    return True
        else:
            print(f'Data for token "{selection[0]}" not found!')
            if len(graphs.keys()) > 0:
                print(f'Try selecting one of these:')
                list_graphs(graphs, '')
    set_status(status, "selected", '')
    return False


def set_status(status, param, value):
    status[param] = value
    save_status(status)


def set_pending_action(status, action, param=None):
    crash_rep = {'action': action}
    if param:
        crash_rep['param'] = param
    if sys.argv:
        crash_rep['cmd'] = ' '.join(sys.argv)
    crash_rep['timestamp'] = time.time()
    status['crash_on'] = crash_rep
    save_status(status)

def clear_crash_rep(status):
    if 'crash_on' in status:
        del status['crash_on']
        save_status(status)


def add_action_history(status, action, success=True, param=None):
    if param is None:
        param = {}
    update = {'type': action, 'success': success, **param, 'timestamp': time.time()}
    status['action_history'].insert(0,update)
    del status['crash_on']
    if len(status['action_history']) > 10:
        status['action_history'].pop()
    save_status(status)


def select_graph_by_index(graphs, index, status):
    found, t, g, c = graph_by_index(graphs, index)
    if found:
        set_status(status, "selected", f'{t}.{g}.{c}')
        return True
    set_status(status, "selected", '')
    return False

def add_to_data(point, to, status):
    gp = status['selected'].split(".")
    file = status['datapath'] + "/" + gp[0] +".json"
    with open(file) as f:
        data = json.load(f)
    timenow = datetime.fromtimestamp(int(time.time()), timezone.utc).strftime(TIME_FORMAT)
    if point[0].lower() == 'now':
        point[0] = timenow
    if point[1].lower() == 'now':
        point[1] = timenow
    x, y = datapoint_to_numbers(point)
    if x == "ERROR" or y == "ERROR":
        print(f'Could not parse datapoint {", ".join(point)}')
        print(f'Please use number, timestamp ({TIME_FORMAT}) or "NOW"')
        return False
    if is_timestamp(point[1]):
        print("PlutusClippy: It seems that you are trying to set a time value to Y axis.")
        r = input(" - Are you sure? Y/n ").strip().lower()

        if r == 'n' or r == 'no':
            print("PlutusClippy: That's what I thought... I could flip the world around for you to fix it... or you can try again.")
            r = input(" - Flip values? Y/n ").strip().lower()
            if r == 'n' or r == 'no':
                print("PlutusClippy: Ok. Bye!")
                return False
            a = point[0]
            point[0] = point[1]
            point[1]  = a
            print("¡ǝuop :ʎddᴉlƆsnʇnlԀ")
        else:
            print("PlutusClippy: Oh. I see...")

    point[0] = string_number_to_number(point[0])
    point[1] = string_number_to_number(point[1])
    if not to:
        data[gp[1]][gp[2]].append(point)
    else:
        to = to[0]
        if to < 0 or to >= len(data[gp[1]][gp[2]]):
            print("Can't add! Index out of range!")
            return False
        data[gp[1]][gp[2]] = data[gp[1]][gp[2]][:to] + [point] + data[gp[1]][gp[2]][to:]
    with open(file, 'w') as f:
        f.write(json.dumps(data, indent=2))
    print(f'Added datapoint {point[0]}, {point[1]} to {gp[0]}.{gp[1]}.{gp[2]}')
    return True


def remove_from_data(index, status):
    gp = status['selected'].split(".")
    file = status['datapath'] + "/" +  gp[0] +".json"
    with open(file) as f:
        data = json.load(f)
    data_len = len(data[gp[1]][gp[2]])
    if index < -data_len or index >= data_len:
        print("Can't delete! No such datapoint!")
        return False
    dp = data[gp[1]][gp[2]][index][:]
    del data[gp[1]][gp[2]][index]
    with open(file, 'w') as f:
        f.write(json.dumps(data, indent=2))
    print("Datapoint deleted!")
    if index < 0:
        index = data_len - index
    print(f'Removed datapoint #{str(index)} ({str(dp[0])}, {str(dp[1])}) from {gp[0]}.{gp[1]}.{gp[2]}')
    return True

def show_graph_data(graphs, status):
    gp = status['selected'].split(".")
    datapoints = graphs[gp[0]][gp[1]][gp[2]]
    i = 0
    print(f'Data for {gp[0]}.{gp[1]}.{gp[2]}')
    first_x = ""
    first_y = ""
    last_x = ""
    last_y = ""
    is_x_dates = False
    for datapoint in datapoints:
        x, y = datapoint_to_numbers(datapoint)
        if x > 1700000000: # assume epoc
            is_x_dates = True
            x = x/(60*60*24)
        else:
            is_x_dates = False
        if y > 1700000000: # assume epoc
            y = y/(60*60*24)
        deltas = ""
        if x != "ERROR" and y != "ERROR":
            if first_x == "":
                first_x = x
                first_y = y
            else:
                d = (y - last_y)/(x - last_x)
                dx = f'{100*(x - last_x):.3f}%'
                dy = f'{100*(y - last_y):.3f}%'
                deltas = f'  |  delta: x: {dx: >20} y: {dy: >20}'

            last_x = x
            last_y = y

        if isinstance(datapoint, list):
            print(f'{i: >3}. x: {datapoint[0]: >20}     y: {datapoint[1]: >20}{deltas}')
        else:
            print(f'{i: >3}. x: {datapoint.x: >20}     y: {datapoint.y: >20}{deltas}')
        i += 1

    if first_x != "" and last_x != "":
        delta = (last_y - first_y)/(last_x - first_x)
        deltas = f'{100*delta:.3f}%'
        td = f'{"": >54} total delta: {deltas: >20}'
        if is_x_dates:
            y_est = delta * 365 * 100
            td += f'  |  Year est:  {y_est:.3f}%'
        print(td)
    return True

def is_int(n):
    try:
        float_n = float(n)
        int_n = int(float_n)
    except ValueError:
        return False
    else:
        return float_n == int_n

def is_float(n):
    try:
        float_n = float(n)
    except ValueError:
        return False
    else:
        return True

def is_timestamp(n):
    try:
        datetime.strptime(n, TIME_FORMAT)
    except ValueError:
        print("error")
        return False
    else:
        return True

def plot_graph_data(graphs, status):
    gp = status['selected'].split(".")
    datapoints = graphs[gp[0]][gp[1]][gp[2]]
    max_x = "unset"
    max_y = "unset"
    min_x = "unset"
    min_y = "unset"
    data = []
    for datapoint in datapoints:
        x, y = datapoint_to_numbers(datapoint)
        if x == "ERROR" or y == "ERROR":
            continue
        data.append([x,y])
        if max_x == "unset" or x > max_x:
            max_x = x
        if min_x == "unset" or x < min_x:
            min_x = x
        if max_y == "unset" or y > max_y:
            max_y = y
        if min_y == "unset" or y < min_y:
            min_y = y
    if min_x == "unset" or max_x == "unset" or min_y == "unset" or max_y =="unset":
        print("Could not plot data..")
        return False
    col = 66
    row = 11
    scaled_data = {}
    print(f'           {gp[0]} {gp[1]} on {gp[2]}')
    print(f'{"": >10} ^')
    for p in data:
        sx = int(((p[0]-min_x)/(max_x-min_x))*(col-1))
        sy = int((row-1)-((p[1]-min_y)/(max_y-min_y))*(row-1))
        if sy not in scaled_data.keys():
            scaled_data[sy] = []
        scaled_data[sy].append(sx)
    for y in range(row):
        r = []
        for x in range(col):
            r.append(" ")
        if y in scaled_data.keys():
            for sx in scaled_data[y]:
                if sx < len(r):
                    if r[sx] == " ":
                        r[sx] = "x"
                    else:
                        r[sx] = "X"
        if y % 2 == 0:
            yvalue = f'{max_y - y*(max_y-min_y)/(row-1):.3f}'
            print(f'{yvalue: >10} +' + "".join(r))
        else:
            print(f'{"": >10} |' + "".join(r))
    lr = f'{" ": >10}  '
    for x in range(col):
        if x % 13 == 0:
            lr += "+"
        else:
            lr += "-"
    lr += ">"
    print(lr)
    lr = f'{" ": >4}  '
    for x in range(int((col+12)/13)):
        xvalue = min_x + x*13*(max_x-min_x)/(col-1)
        if xvalue > 1700000000: # assume epoc
            xvalue = datetime.fromtimestamp(int(xvalue)).strftime('%m-%d %H:%M')
            lr += f'{xvalue: ^13}'
        else:
            xvalue = f'{xvalue:.3f}'
            lr += f'{xvalue: ^13}'
    print(lr)
    return True


def datapoint_to_numbers(datapoint):
    if isinstance(datapoint, list):
        x = datapoint_value_to_number(datapoint[0])
        y = datapoint_value_to_number(datapoint[1])
    else:
        x = datapoint_value_to_number(datapoint.x)
        y = datapoint_value_to_number(datapoint.y)
    return x, y


def string_number_to_number(n):
    if isinstance(n, str):
        if is_int(n):
            return float(n)
        if is_float(n):
            return float(n)
    return n

def datapoint_value_to_number(dpv):
    if isinstance(dpv, str):
        if is_int(dpv):
            return float(dpv)
        if is_float(dpv):
            return float(dpv)
        if is_timestamp(dpv):
            return datetime.strptime(dpv, TIME_FORMAT).timestamp()
    if isinstance(dpv, int):
        return float(dpv)
    if isinstance(dpv, float):
        return dpv
    return "ERROR"

def fetch_updates(status, force=False):
    cwd = os.getcwd()
    os.chdir(status['datapath'])
    output = subprocess.check_output(['git', 'status', '.'])
    if 'nothing to commit' in str(output) or force:
        if status['last_update'] + 600 <= time.time() or force:
            out = subprocess.run(['git', 'checkout', "."], stdout=open(os.devnull, 'wb'))
            if out.returncode != 0:
                os.chdir(cwd)
                print('Failed to update graphs! Please fix.')
                return False, True
            set_status(status, 'last_update', time.time())
            os.chdir(cwd)
            return True, True
    os.chdir(cwd)
    return True, False


def check_git_status(status):
    cwd = os.getcwd()
    os.chdir(status['datapath'])
    output = subprocess.check_output(['git', 'status' , '--', "':!.'"])
    os.chdir(cwd)
    if 'nothing to commit' not in str(output):
        return False
    return True

def commit_changes(status):
    cwd = os.getcwd()
    os.chdir(status['datapath'])
    output = subprocess.check_output(['git', 'status', '.'])
    if 'nothing to commit' in str(output):
        os.chdir(cwd)
        print('You have no changes to commit...')
        return True, False
    subprocess.run(['git', 'add' , '.'], stdout=open(os.devnull, 'wb'))
    subprocess.run(['git', 'commit', '-m' 'pUD: Update graph values.'], stdout=open(os.devnull, 'wb'))
    os.chdir(cwd)
    return True, True


def push_changes(status):
    cwd = os.getcwd()
    os.chdir(status['datapath'])
    output = subprocess.check_output(['git', 'status', '.'])
    commited = 'nothing to commit' not in str(output)
    if commited:
        print('Commiting unsaved changes before push..')
        subprocess.run(['git', 'add' , '.'], stdout=open(os.devnull, 'wb'))
        subprocess.run(['git', 'commit', '-m' 'pUD: Update graph values.'], stdout=open(os.devnull, 'wb'))
    if 'Your branch is ahead' in str(output):
        out = subprocess.run(['git', 'push'], stdout=open(os.devnull, 'wb'))
        os.chdir(cwd)
        if out.returncode != 0:
            print("Failed to push changes! please fix")
            return False, False, commited
    else:
        print('You have no changes to push.')
        return True, False, commited
    return True, True, commited

def main(args, status):
    ret = do_actions(args, status)
    clear_crash_rep(status)
    return ret


def do_actions(args, status):
    if args.update:
        if args.update[0] == 'a' or args.update[0] == 'auto':
            set_pending_action(status, 'update', args.update)
            success, updated = fetch_updates(status)
            if updated or not success:
                add_action_history(status, "update", success, {'arg': 'auto', 'updated': updated})
            if not success:
                return 1
        if args.update[0] == 'f' or args.update[0] == 'force':
            set_pending_action(status, 'update', args.update)
            success, updated = fetch_updates(status, True)
            add_action_history(status, "update", success, {'arg': 'force', 'updated': updated})
            if not success:
                return 1
    if args.add or args.remove or args.commit or args.push:
        set_pending_action(status, 'check-git-status')
        if not check_git_status(status):
            print('You have unsaved changes in your local repository, please commit or stash them before updating data..')
            return 1

    set_pending_action(status, 'get-graphs')
    graphs = get_graphs(status['datapath'])
    if args.list_info:
        set_pending_action(status, 'list-info')
        list_graphs(graphs, status['selected'], True)
    elif args.list:
        set_pending_action(status, 'list')
        list_graphs(graphs, status['selected'])
    if args.select:
        sel_before = status['selected']
        set_pending_action(status, 'select', args.select)
        if len(args.select) == 1 and is_int(args.select[0]):
            success = select_graph_by_index(graphs, int(args.select[0]), status)
            if status['selected'] != sel_before or not success:
                add_action_history(status, "select", success, {'by': 'index', 'args': args.select})
            if success:
                print(f'Selected: {" > ".join(status["selected"].split("."))}')
            else:
                print(f'Graph selection with index {args.select[0]} failed')
                print(f'Try selecting one of these:')
                set_pending_action(status, 'list')
                list_graphs(graphs, '')
                return 1
        else:
            success = select_graph(graphs, args.select, status)
            if status['selected'] != sel_before or not success:
                add_action_history(status, "select", success, {'by': 'identifier', 'args': args.select})
            if success:
                print(f'Selected: {" > ".join(status["selected"].split("."))}')
            else:
                return 1
    if args.add or args.remove or args.data or args.plot:
        if status['selected'] == '':
            print('You must select a graph first...')
            return 1
    if args.add:
        to = []
        if args.to:
            to = args.to
        set_pending_action(status, 'add', args.add + to)
        success = add_to_data(args.add, args.to, status)
        add_action_history(status, "add", success, {'coords': args.add, 'to': args.to, 'selected': status['selected']})
        if not success:
            return 1
        set_pending_action(status, 'get-graphs')
        graphs = get_graphs(status['datapath'])
    elif args.to:
        print('--to only works with --add')
        return 1
    if args.remove:
        set_pending_action(status, 'remove', args.remove)
        success = remove_from_data(args.remove[0], status)
        add_action_history(status, "remove", success, {'index': args.remove[0], 'selected': status['selected']})
        if not success:
            return 1
        set_pending_action(status, 'get-graphs')
        graphs = get_graphs(status['datapath'])
    if args.data:
        set_pending_action(status, 'list-data')
        success = show_graph_data(graphs, status)
        add_action_history(status, "list-data", success, {'selected': status['selected']})
    if args.plot:
        set_pending_action(status, 'plot')
        success = plot_graph_data(graphs, status)
        add_action_history(status, "plot", success, {'selected': status['selected']})
    if args.commit:
        set_pending_action(status, 'commit')
        success, commited = commit_changes(status)
        add_action_history(status, "commit", success, {'commited': commited})
        if not success:
            return 1
    if args.push:
        set_pending_action(status, 'push')
        success, pushed, commited = push_changes(status)
        add_action_history(status, "push", success, {'pushed': pushed, 'commited': commited})
        if not success:
            return 1
    return 0





if __name__ == '__main__':
    main(read_args(), read_status())

