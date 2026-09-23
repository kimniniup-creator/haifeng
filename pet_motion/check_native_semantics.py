import ast,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import argparse
parser=argparse.ArgumentParser(description='Offline AST-only native backend semantics checks; never imports the SDK.')
parser.add_argument('backend_root', type=Path)
root=parser.parse_args().backend_root
def extract(path,name):
    data=path.read_bytes(); tree=ast.parse(data)
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    node.returns=None;node.decorator_list=[]
    for a in node.args.args: a.annotation=None
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    env={'np':np};exec(compile(module,str(path),'exec'),env)
    return env[name],hashlib.sha256(data).hexdigest()
f,h=extract(root/'abstract.py','update_target_head_joints_from_ik')
s=SimpleNamespace(target_head_pose=np.eye(4),target_body_yaw=0.,_speech_offsets=[0.]*6,head_kinematics=SimpleNamespace(ik=Mock(return_value=np.arange(7.))),ik_required=True)
f(s)
assert s.ik_required is True
assert np.array_equal(s.target_head_joint_positions,np.arange(7.))
assert np.array_equal(s._last_target_head_pose,np.eye(4))
u,rh=extract(root/'robot/backend.py','_update')
def stub(torque,mode):
    return SimpleNamespace(c=Mock(),_torque_enabled=torque,_current_head_operation_mode=mode,target_head_joint_positions=np.arange(7.),_current_antennas_operation_mode=3,target_antenna_joint_positions=np.array([.1,.2]),joint_positions_publisher=None,pose_publisher=None,gravity_compensation_mode=False,target_head_joint_current=None)
a=stub(True,3);u(a);a.c.set_stewart_platform_position.assert_called_once_with([1.,2.,3.,4.,5.,6.]);a.c.set_body_rotation.assert_called_once_with(0.)
b=stub(False,3);u(b);b.c.set_stewart_platform_position.assert_not_called()
c=stub(True,0);u(c);c.c.set_stewart_platform_position.assert_not_called()
print(json.dumps({'checks_passed':4,'abstract_sha256':h,'robot_backend_sha256':rh,'checks':['successful IK retains true flag and updates targets','position loop passes target to fake controller','disabled internal torque skips position dispatch','current mode skips position dispatch'],'hardware_imports':False}))
