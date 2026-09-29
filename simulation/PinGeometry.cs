using System;
using SolidWorks.Interop.sldworks;

partial class SimulationBridge
{
    static System.Collections.Generic.Dictionary<string,object> MakePin(ISldWorks app,System.Collections.Generic.Dictionary<string,object> p)
    {
        var model=Model(app,p);var part=(IPartDoc)model;
        var oldBodies=Objects(part.GetBodies2(0,false));
        Require(oldBodies.Length>=1&&oldBodies.Length<=2,"PIN_BODY_COUNT_UNEXPECTED");
        var face=Keep((IFace2)FaceById(model,Arg(p,"sketch_face")));
        var surface=Keep((ISurface)face.GetSurface());Require(surface.IsPlane(),"PIN_SKETCH_FACE_NOT_PLANAR");
        double[] center=Triple(p["center_mm"],"center_mm");
        double radius=Convert.ToDouble(p["radius_mm"]),length=Convert.ToDouble(p["length_mm"]);
        Require(radius>0&&radius<100&&length>0&&length<100,"PIN_DIMENSIONS_INVALID");
        string name=Arg(p,"name");Require(!String.IsNullOrWhiteSpace(name)&&name.Length<=50,"PIN_NAME_INVALID");
        var plane=Numbers(surface.PlaneParams);var outward=plane[1]*(face.FaceInSurfaceSense()?-1:1);
        Require(Math.Abs(outward+1)<1e-6,"PIN_FACE_MUST_POINT_NEGATIVE_Y");
        Require(Math.Abs(center[1]-plane[4]*1000)<1e-4,"PIN_CENTER_NOT_ON_SKETCH_FACE");
        model.ClearSelection2(true);Require(((IEntity)face).Select4(false,null),"PIN_FACE_SELECTION_FAILED");
        var sm=Keep((ISketchManager)model.SketchManager);
        MutationStarted=true;Call("InsertSketch(pin)",()=>{sm.InsertSketch(true);return true;});
        var sketch=Keep((ISketch)model.GetActiveSketch2());Require(sketch!=null,"PIN_SKETCH_START_FAILED");
        var utility=Keep((IMathUtility)app.GetMathUtility());
        var world=Keep((IMathPoint)utility.CreatePoint(new[]{center[0]/1000,center[1]/1000,center[2]/1000}));
        var local=Numbers(Keep((IMathPoint)world.MultiplyTransform(Keep(sketch.ModelToSketchTransform))).ArrayData);
        Require(Math.Abs(local[2])<1e-7,"PIN_CENTER_OFF_SKETCH_PLANE");
        var circle=Keep((ISketchSegment)Call("CreateCircleByRadius(pin)",()=>sm.CreateCircleByRadius(local[0],local[1],0,radius/1000)));
        Require(circle!=null,"PIN_CIRCLE_FAILED");
        Call("CloseSketch(pin)",()=>{sm.InsertSketch(true);return true;});
        Require(model.GetActiveSketch2()==null,"PIN_SKETCH_CLOSE_FAILED");
        var fm=Keep((IFeatureManager)model.FeatureManager);
        var feature=Keep((IFeature)Call("FeatureExtrusion3(separate pin body)",()=>fm.FeatureExtrusion3(true,false,true,0,0,length/1000,0,
            false,false,false,false,0,0,false,false,false,false,false,false,true,0,0,false)));
        Require(feature!=null,"PIN_EXTRUSION_FAILED");feature.Name=name;
        var newBodies=Objects(part.GetBodies2(0,false));Require(newBodies.Length==oldBodies.Length+1,"PIN_BODY_NOT_SEPARATE");
        var faces=Objects(feature.GetFaces());Require(faces.Length>0,"PIN_FEATURE_FACES_MISSING");
        var body=Keep((IBody2)((IFace2)faces[0]).GetBody());body.Name=name;
        Require(body.Name==name,"PIN_BODY_NAME_READBACK_FAILED");
        var cylinderCount=0;foreach(var raw in Objects(body.GetFaces())){var f=Keep((IFace2)raw);var s=Keep((ISurface)f.GetSurface());
            if(s.IsCylinder()){
                cylinderCount++;var cp=Numbers(s.CylinderParams);
                Require(Math.Abs(cp[6]*1000-radius)<1e-4,"PIN_RADIUS_READBACK_FAILED");
                Require(Math.Abs(cp[0]*1000-center[0])<1e-4&&Math.Abs(cp[2]*1000-center[2])<1e-4,"PIN_AXIS_POSITION_READBACK_FAILED");
                Require(Math.Abs(Math.Abs(cp[4])-1)<1e-6,"PIN_AXIS_DIRECTION_FAILED");
            }
        }
        Require(cylinderCount>=1,"PIN_CYLINDER_MISSING");
        return D("status","success","feature",feature.Name,"body",body.Name,"radius_mm",radius,"length_mm",length,
            "body_count",newBodies.Length,"pin_cylindrical_faces",cylinderCount,"dirty",model.GetSaveFlag());
    }
}
