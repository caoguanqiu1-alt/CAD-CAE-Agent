using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.cosworks;

// Short-lived STA bridge. Attach only; never start/quit SOLIDWORKS.
// The calling MCP holds the existing process-wide COM lock for the entire call.
partial class SimulationBridge
{
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 50000000 };
    static readonly List<object> Owned = new List<object>();
    static string Step = "initialize";
    static bool MutationStarted;
    static T Keep<T>(T value) { if (value != null && Marshal.IsComObject(value) && !Owned.Any(x => Object.ReferenceEquals(x,value))) Owned.Add(value); return value; }
    static T Call<T>(string step, Func<T> action) { Step=step; Console.Error.WriteLine(DateTime.UtcNow.ToString("o")+" "+step); return action(); }
    static Dictionary<string,object> D(params object[] pairs) { var d=new Dictionary<string,object>(); for(int i=0;i<pairs.Length;i+=2)d[(string)pairs[i]]=pairs[i+1]; return d; }
    static string Arg(Dictionary<string,object> p,string key,string fallback="") {return p.ContainsKey(key)?Convert.ToString(p[key]):fallback;}
    static bool Flag(Dictionary<string,object> p,string key) {return p.ContainsKey(key)&&Convert.ToBoolean(p[key]);}
    static void Require(bool condition,string message) {if(!condition)throw new InvalidOperationException(message);}
    static string Install(Dictionary<string,object> p) { return Arg(p,"install_dir",@"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"); }
    static ISldWorks Attach(Dictionary<string,object> p)
    {
        object raw=Call("Marshal.GetActiveObject(SldWorks.Application.28)",()=>Marshal.GetActiveObject("SldWorks.Application.28"));
        var app=Keep((ISldWorks)raw);
        Require(Call("RevisionNumber",()=>app.RevisionNumber()).Split('.')[0]=="28","WRONG_VERSION: expected SOLIDWORKS 2020");
        if(p.ContainsKey("expected_pid"))Require(Call("GetProcessID",()=>app.GetProcessID())==Convert.ToInt32(p["expected_pid"]),"WRONG_INSTANCE");
        return app;
    }
    static IModelDoc2 Model(ISldWorks app,Dictionary<string,object> p)
    {
        var m=Keep((IModelDoc2)Call("ActiveDoc",()=>app.ActiveDoc));
        Require(m!=null,"NO_ACTIVE_DOCUMENT");
        Require(Call("Document.GetType",()=>m.GetType())==1,"DOCUMENT_NOT_PART");
        var expected=Arg(p,"expected_document");
        Require(!String.IsNullOrWhiteSpace(expected)&&String.Equals(Call("GetPathName",()=>m.GetPathName()),expected,StringComparison.OrdinalIgnoreCase),"DOCUMENT_MISMATCH: expected absolute active document path");
        Require(Keep(Call("GetActiveSketch2",()=>m.GetActiveSketch2()))==null,"SKETCH_EDITING");
        return m;
    }
    static ICosmosWorks Cosmos(ISldWorks app,Dictionary<string,object> p,Dictionary<string,object> diag)
    {
        string dll=Path.Combine(Install(p),"Simulation","cosworks.dll");
        diag["simulation_installed"]=File.Exists(dll);
        diag["simulation_loaded"]=false; diag["simulation_api_available"]=false;
        diag["simulation_license_status"]="not_independently_verified";
        object callback=null;
        foreach(string name in new[]{"SldWorks.Simulation","CosmosWorks.CosmosWorks"}) {
            try {callback=Keep(Call("GetAddInObject("+name+")",()=>app.GetAddInObject(name)));} catch(COMException ex){diag["addin_probe_error"]=ex.Message;}
            if(callback!=null){diag["addin_progid"]=name;break;}
        }
        if(callback==null && Flag(p,"load_addin") && File.Exists(dll)) {
            diag["load_addin_return_code"]=Call("LoadAddIn(cosworks.dll)",()=>app.LoadAddIn(dll));
            foreach(string name in new[]{"SldWorks.Simulation","CosmosWorks.CosmosWorks"}) {
                try {callback=Keep(Call("GetAddInObject("+name+")",()=>app.GetAddInObject(name)));}catch(COMException ex){diag["addin_probe_error"]=ex.Message;}
                if(callback!=null){diag["addin_progid"]=name;break;}
            }
        }
        if(callback==null){diag["error_code"]=File.Exists(dll)?"SIMULATION_NOT_LOADED":"SIMULATION_NOT_INSTALLED";diag["message"]="Add-in unavailable; license availability cannot be inferred from this alone."; return null;}
        diag["simulation_loaded"]=true;
        var cb=(ICwAddincallback)callback;
        var cw=Keep((ICosmosWorks)Call("CwAddincallback.CosmosWorks",()=>cb.CosmosWorks));
        if(cw==null){diag["error_code"]="SIMULATION_API_UNAVAILABLE";return null;}
        diag["simulation_api_available"]=true;
        diag["simulation_version"]=Call("CosmosWorks.VersionNumber",()=>cw.VersionNumber);
        return cw;
    }
    static Dictionary<string,object> Check(ISldWorks app,Dictionary<string,object> p)
    {
        var d=D("solidworks_connected",true,"solidworks_version","2020","revision",app.RevisionNumber(),"process_id",app.GetProcessID());
        var m=Keep((IModelDoc2)Call("ActiveDoc",()=>app.ActiveDoc));
        d["document_open"]=m!=null; d["document_type"]=m==null?null:(m.GetType()==1?"part":"not_part");
        d["document_path"]=m==null?null:m.GetPathName();d["document_dirty"]=m==null?null:(object)m.GetSaveFlag();
        Cosmos(app,p,d);
        if(!d.ContainsKey("error_code") && m==null)d["error_code"]="NO_ACTIVE_DOCUMENT";
        if(!d.ContainsKey("error_code") && m!=null && m.GetType()!=1)d["error_code"]="DOCUMENT_NOT_PART";
        d["status"]=d.ContainsKey("error_code")?"error":"success";return d;
    }
    static Dictionary<string,object> Study(ISldWorks app,Dictionary<string,object> p)
    {
        var model=Model(app,p);var d=D();var cw=Cosmos(app,p,d);if(cw==null){d["status"]="error";return d;}
        var doc=Keep((ICWModelDoc)Call("CosmosWorks.ActiveDoc",()=>cw.ActiveDoc));Require(doc!=null,"SIMULATION_NO_ACTIVE_DOCUMENT");
        var mgr=Keep((ICWStudyManager)Call("CWModelDoc.StudyManager",()=>doc.StudyManager));
        string name=Arg(p,"name","Static_API_Test");Require(!String.IsNullOrWhiteSpace(name)&&name.Length<=80,"INVALID_STUDY_NAME");
        int count=Call("StudyCount",()=>mgr.StudyCount); ICWStudy found=null;int index=-1;
        for(int i=0;i<count;i++){int j=i;var s=Keep((ICWStudy)Call("GetStudy",()=>mgr.GetStudy(j)));if(String.Equals(s.Name,name,StringComparison.OrdinalIgnoreCase)){found=s;index=i;break;}}
        bool created=found==null;
        if(created){Require(!model.GetSaveFlag(),"DIRTY_DOCUMENT: save/review changes before creating study");int err=0;MutationStarted=true;
            found=Keep((ICWStudy)Call("CreateNewStudy3",()=>mgr.CreateNewStudy3(name,(int)swsAnalysisStudyType_e.swsAnalysisStudyTypeStatic,0,out err)));
            d["study_error_code"]=err;d["study_error_name"]=Enum.GetName(typeof(swsStudyError_e),err)??"Unknown";
            Require(err==0&&found!=null,"STUDY_CREATE_FAILED: "+d["study_error_name"]);index=mgr.StudyCount-1;
        }
        Require(found.AnalysisType==(int)swsAnalysisStudyType_e.swsAnalysisStudyTypeStatic,"EXISTING_STUDY_NOT_STATIC");
        Call("SetActiveStudy",()=>{mgr.ActiveStudy=index;return true;});
        var reread=Keep((ICWStudy)Call("GetStudy(readback)",()=>mgr.GetStudy(index)));
        Require(reread!=null&&reread.Name==found.Name&&reread.AnalysisType==0,"STUDY_READBACK_FAILED");
        d["status"]="success";d["study"]=reread.Name;d["analysis_type"]=reread.AnalysisType;d["created"]=created;d["study_count"]=mgr.StudyCount;d["active_study_index"]=mgr.ActiveStudy;d["document_path"]=model.GetPathName();d["dirty"]=model.GetSaveFlag();return d;
    }
    static double[] Numbers(object x) {return ((Array)x).Cast<object>().Select(Convert.ToDouble).ToArray();}
    static object[] Objects(object x){return x==null?new object[0]:((Array)x).Cast<object>().ToArray();}
    static Dictionary<string,object> Identity(IModelDocExtension ext,object entity,string kind)
    {
        var bytes=(byte[])Call("GetPersistReference3("+kind+")",()=>ext.GetPersistReference3(entity));
        Require(bytes!=null&&bytes.Length>0,"PERSIST_REFERENCE_EMPTY");int error=0;
        var resolved=Keep(Call("GetObjectByPersistReference3("+kind+")",()=>ext.GetObjectByPersistReference3(bytes,out error)));
        Require(error==0&&resolved!=null,"PERSIST_REFERENCE_RESOLUTION_FAILED: "+error);
        string b64=Convert.ToBase64String(bytes);return D("id",kind+"_"+b64,"persistent_reference_base64",b64,"resolve_error",error);
    }
    static Dictionary<string,object> Geometry(ISldWorks app,Dictionary<string,object> p)
    {
        var model=Model(app,p);var ext=Keep(model.Extension);var part=(IPartDoc)model;
        var faces=new List<object>();var edges=new List<object>();var vertices=new List<object>();
        var bodies=Objects(Call("GetBodies2",()=>part.GetBodies2(0,false)));int bodyIndex=0;
        foreach(var raw in bodies){var body=Keep((IBody2)raw);bodyIndex++;
            foreach(var f in Objects(Call("Body.GetFaces",()=>body.GetFaces()))){var face=Keep((IFace2)f);var row=Identity(ext,face,"face");var surf=Keep((ISurface)Call("Face.GetSurface",()=>face.GetSurface()));
                bool planar=Call("Surface.IsPlane",()=>surf.IsPlane()),cyl=Call("Surface.IsCylinder",()=>surf.IsCylinder());
                row["label"]="F"+(faces.Count+1).ToString("D3");row["body_index"]=bodyIndex;row["type"]=planar?"planar":cyl?"cylindrical":"other";
                row["area_mm2"]=Call("Face.GetArea",()=>face.GetArea())*1e6;
                var box=Numbers(Call("Face.GetBox",()=>face.GetBox()));row["bbox_mm_approx"]=box.Select(v=>v*1000).ToArray();
                row["center_mm"]=new[]{(box[0]+box[3])*500,(box[1]+box[4])*500,(box[2]+box[5])*500};row["center_method"]="approximate_bounding_box_midpoint_not_area_centroid";
                var feature=Keep((IFeature)Call("Face.GetFeature",()=>face.GetFeature()));row["feature"]=feature==null?null:feature.Name;
                if(planar){var v=Numbers(Call("Surface.PlaneParams",()=>surf.PlaneParams));bool reverse=Call("FaceInSurfaceSense",()=>face.FaceInSurfaceSense());row["normal"]=v.Take(3).Select(a=>reverse?-a:a).ToArray();row["plane_origin_mm"]=v.Skip(3).Take(3).Select(a=>a*1000).ToArray();}
                if(cyl){var v=Numbers(Call("Surface.CylinderParams",()=>surf.CylinderParams));row["axis_origin_mm"]=v.Take(3).Select(a=>a*1000).ToArray();row["axis"]=v.Skip(3).Take(3).ToArray();row["radius_mm"]=v[6]*1000;}
                faces.Add(row);
            }
            foreach(var e in Objects(Call("Body.GetEdges",()=>body.GetEdges()))){var edge=Keep((IEdge)e);var row=Identity(ext,edge,"edge");row["label"]="E"+(edges.Count+1).ToString("D3");row["body_index"]=bodyIndex;edges.Add(row);}
            foreach(var v in Objects(Call("Body.GetVertices",()=>body.GetVertices()))){var vertex=Keep((IVertex)v);var row=Identity(ext,vertex,"vertex");row["label"]="V"+(vertices.Count+1).ToString("D3");row["body_index"]=bodyIndex;row["point_mm"]=Numbers(Call("Vertex.GetPoint",()=>vertex.GetPoint())).Select(a=>a*1000).ToArray();vertices.Add(row);}
        }
        return D("status","success","document_path",model.GetPathName(),"configuration",Keep(model.ConfigurationManager).ActiveConfiguration.Name,"solid_bodies",bodies.Length,"faces",faces,"edges",edges,"vertices",vertices,"units","mm, mm2","identity_scope","document and configuration; labels are inspection-local; use persistent IDs; topology edits may invalidate references");
    }
    static Dictionary<string,object> Resolve(ISldWorks app,Dictionary<string,object> p)
    {
        var model=Model(app,p);var ext=Keep(model.Extension);var rows=new List<object>();var entities=new List<IEntity>();
        Require(p.ContainsKey("ids"),"MISSING_IDS");
        foreach(var value in (System.Collections.IEnumerable)p["ids"]){string id=Convert.ToString(value);int split=id.IndexOf('_');Require(split>0,"INVALID_ENTITY_ID");
            string kind=id.Substring(0,split);Require(kind=="face"||kind=="edge"||kind=="vertex","INVALID_ENTITY_KIND");
            var bytes=Convert.FromBase64String(id.Substring(split+1));int err=0;var entity=Keep(Call("GetObjectByPersistReference3(saved ID)",()=>ext.GetObjectByPersistReference3(bytes,out err)));
            Require(err==0&&entity!=null,"PERSIST_REFERENCE_STALE: "+err);
            Require((kind=="face"&&entity is IFace2)||(kind=="edge"&&entity is IEdge)||(kind=="vertex"&&entity is IVertex),"ENTITY_TYPE_MISMATCH");
            entities.Add((IEntity)entity);rows.Add(D("id",id,"resolved",true,"resolve_error",err));
        }
        int selectedCount=0;
        if(Flag(p,"highlight")) {Call("ClearSelection2",()=>{model.ClearSelection2(true);return true;});foreach(var entity in entities)Require(Call("Entity.Select4",()=>entity.Select4(true,null)),"SELECTION_FAILED");
            var selection=Keep((ISelectionMgr)model.SelectionManager);selectedCount=Call("Selection.GetSelectedObjectCount2",()=>selection.GetSelectedObjectCount2(-1));Require(selectedCount==entities.Count,"SELECTION_READBACK_FAILED");
        }
        return D("status","success","entities",rows,"highlighted",Flag(p,"highlight"),"selected_count",selectedCount,"count",rows.Count);
    }
    static Dictionary<string,object> Dispatch(Dictionary<string,object> p)
    {
        if(System.Diagnostics.Process.GetProcessesByName("SLDWORKS").Length==0)
            return D("status","error","error_code","SOLIDWORKS_NOT_RUNNING","solidworks_connected",false,"solidworks_version",null,"document_open",false,"document_type",null,"simulation_installed",File.Exists(Path.Combine(Install(p),"Simulation","cosworks.dll")),"simulation_loaded",false,"simulation_api_available",false,"simulation_license_status","unknown");
        var app=Attach(p);string op=Arg(p,"operation");
        if(op=="check")return Check(app,p);
        if(op=="inspect_geometry")return Geometry(app,p);
        if(op=="resolve_geometry")return Resolve(app,p);
        if(op=="create_static_study")return Study(app,p);
        if(op.StartsWith("phase2_"))return Phase2(app,p);
        if(op=="phase3_make_pin")return MakePin(app,p);
        if(op.StartsWith("phase3_"))return Phase3(app,p);
        // Administrative operations used by the integration runner on its own copy.
        if(op=="open") {string path=Arg(p,"path");Require(File.Exists(path),"FILE_NOT_FOUND");int err=0,warn=0;var model=Keep(Call("OpenDoc6",()=>app.OpenDoc6(path,1,1,"",ref err,ref warn)));Require(model!=null&&err==0,"OPEN_FAILED: "+err);int ae=0;Keep(Call("ActivateDoc3",()=>app.ActivateDoc3(path,false,0,ref ae)));return D("status","success","document_path",model.GetPathName(),"errors",err,"warnings",warn);}
        if(op=="save") {var m=Model(app,p);int e=0,w=0;MutationStarted=true;bool ok=Call("Save3",()=>m.Save3(1,ref e,ref w));Require(ok&&e==0,"SAVE_FAILED: "+e);return D("status","success","errors",e,"warnings",w,"dirty",m.GetSaveFlag());}
        if(op=="close_clean_copy") {var m=Model(app,p);Require(!m.GetSaveFlag(),"DIRTY_DOCUMENT: refusing close");string path=m.GetPathName();Call("CloseDoc(clean test copy)",()=>{app.CloseDoc(path);return true;});return D("status","success","closed",path);}
        if(op=="preview") {var m=Model(app,p);string path=Arg(p,"path");Require(!File.Exists(path),"OUTPUT_EXISTS");Call("ShowNamedView2",()=>{if(Flag(p,"clear_selection"))m.ClearSelection2(true);m.ShowNamedView2("",7);m.ViewZoomtofit2();return true;});Require(Call("SaveBMP",()=>m.SaveBMP(path,1400,900)),"PREVIEW_FAILED");return D("status","success","path",path);}
        throw new InvalidOperationException("UNKNOWN_OPERATION");
    }
    [STAThread] static int Main()
    {
        Console.InputEncoding=System.Text.Encoding.UTF8;Console.OutputEncoding=new System.Text.UTF8Encoding(false);
        try {var p=Json.Deserialize<Dictionary<string,object>>(Console.In.ReadToEnd());Console.WriteLine(Json.Serialize(Dispatch(p)));return 0;}
        catch(Exception ex) {string code=ex is COMException?"API_COM_FAILED":"API_FAILED";
            if(ex is InvalidOperationException){string candidate=ex.Message.Split(':')[0];if(System.Text.RegularExpressions.Regex.IsMatch(candidate,"^[A-Z][A-Z0-9_]+$"))code=candidate;}
            if(ex is FormatException)code="INVALID_PERSIST_REFERENCE";
            Console.WriteLine(Json.Serialize(D("status",MutationStarted?"unknown":"error","error_code",code,"stage",Step,"message",ex.Message,"hresult","0x"+ex.HResult.ToString("X8"),"requires_inspection",MutationStarted)));return 1;}
        finally {for(int i=Owned.Count-1;i>=0;i--)try{Marshal.ReleaseComObject(Owned[i]);}catch(Exception ex){Console.Error.WriteLine("COM release: "+ex.Message);}}
    }
}
