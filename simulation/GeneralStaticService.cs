using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.cosworks;

partial class SimulationBridge
{
    static double[] Triple(object value, string code)
    {
        var raw=value as IEnumerable;Require(raw!=null,"INVALID_VECTOR: "+code);
        var values=new List<double>();foreach(var item in raw)values.Add(Convert.ToDouble(item));
        Require(values.Count==3&&values.All(v=>!Double.IsNaN(v)&&!Double.IsInfinity(v)),"INVALID_VECTOR: "+code);
        return values.ToArray();
    }
    static double Dot(double[] a,double[] b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
    static double Norm(double[] a){return Math.Sqrt(Dot(a,a));}
    static List<ICWSolidBody> StudyBodies(ICWStudy study)
    {
        var manager=Keep((ICWSolidManager)study.SolidManager);Require(manager.ComponentCount==1,"PART_COMPONENT_REQUIRED");
        int error=0;var component=Keep((ICWSolidComponent)manager.GetComponentAt(0,out error));
        Require(error==0&&component!=null,"COMPONENT_ERROR");
        var bodies=new List<ICWSolidBody>();for(int i=0;i<component.SolidBodyCount;i++){
            var body=Keep((ICWSolidBody)component.GetSolidBodyAt(i,out error));Require(error==0&&body!=null,"SOLID_BODY_ERROR");bodies.Add(body);
        }
        return bodies;
    }
    static double[] PlaneBasis(ISldWorks app,IRefPlane plane,int index)
    {
        var util=Keep((IMathUtility)app.GetMathUtility());var basis=new double[3];basis[index]=1;
        var v=Keep((IMathVector)util.CreateVector(basis));
        return Numbers(Keep((IMathVector)v.MultiplyTransform(Keep(plane.Transform))).ArrayData);
    }
    static Dictionary<string,object> Phase3(ISldWorks app,Dictionary<string,object> p)
    {
        var model=Model(app,p);var study=ExistingStudy(app,p);
        var lm=Keep((ICWLoadsAndRestraintsManager)study.LoadsAndRestraintsManager);
        string op=Arg(p,"operation");var d=D("status","success","study",study.Name);
        if(op=="phase3_state"){
            d["boundaries"]=BoundaryState(lm);
            var mesh=Keep((ICWMesh)study.Mesh);d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;
            var contacts=Keep((ICWContactManager)study.ContactManager);d["contact_count"]=contacts.ContactSetCount;
            int globalType=0,globalOption=0;contacts.GetGlobalContact(out globalType,out globalOption);
            d["global_contact_type"]=globalType;d["global_contact_option"]=globalOption;
            var cs=new List<object>();for(int i=0;i<contacts.ContactSetCount;i++){
                var c=Keep((ICWContactSet)contacts.GetContactSetAt(i));cs.Add(D("name",c.ContactName,"type",c.ContactSetType,"source_count",c.SourceEntityCount,"target_count",c.TargetEntityCount));
            }d["contacts"]=cs;d["result_folder"]=Keep((ICWStaticStudyOptions)study.StaticStudyOptions).ResultFolder;d["dirty"]=model.GetSaveFlag();return d;
        }
        if(op=="phase3_materials"){
            string library=Arg(p,"library"),name=Arg(p,"material");Require(System.IO.File.Exists(library),"MATERIAL_LIBRARY_MISSING");
            Require(!String.IsNullOrWhiteSpace(name),"MATERIAL_NAME_REQUIRED");
            var bodies=StudyBodies(study);Require(bodies.Count>=2,"MULTIBODY_REQUIRED");
            var materials=new List<object>();
            foreach(var body in bodies){
                var mat=Keep((ICWMaterial)body.GetSolidBodyMaterial());int error=0;
                if(mat==null||mat.MaterialName!=name){MutationStarted=true;error=Call("SetLibraryMaterial(multibody)",()=>body.SetLibraryMaterial(library,name));mat=Keep((ICWMaterial)body.GetSolidBodyMaterial());}
                Require(mat!=null&&mat.MaterialName==name,"MATERIAL_LIBRARY_MATCH_FAILED: "+error);
                mat.ModelType=(int)swsMaterialModelType_e.swsMaterialModelTypeLinearElasticIsotropic;MutationStarted=true;
                error=Call("SetSolidBodyMaterial(multibody)",()=>body.SetSolidBodyMaterial((CWMaterial)mat));Require(error==0,"MATERIAL_SET_FAILED: "+error);
                materials.Add(MaterialData(body));
            }
            d["solid_body_count"]=bodies.Count;d["materials"]=materials;return d;
        }
        if(op=="phase3_forces"){
            Require(lm.Count==1,"EXPECTED_ONE_FIXTURE: inspect study before applying load set");
            int fixtureError=0;var first=Keep((ICWLoadsAndRestraints)lm.GetLoadsAndRestraints(0,out fixtureError));
            Require(fixtureError==0&&first!=null&&first.Type==2,"FIXED_FIXTURE_REQUIRED");
            var rows=p.ContainsKey("loads")?p["loads"] as IEnumerable:null;Require(rows!=null,"LOADS_REQUIRED");
            var planned=new List<Tuple<IFace2,double[],double[]>>();
            var feature=Keep((IFeature)((IPartDoc)model).FeatureByName("Right Plane"));
            if(feature==null)feature=Keep((IFeature)((IPartDoc)model).FeatureByName("右视基准面"));
            if(feature==null)feature=Keep((IFeature)((IPartDoc)model).FeatureByName("右視基準面"));
            Require(feature!=null,"RIGHT_PLANE_NOT_FOUND");
            var plane=Keep((IRefPlane)feature.GetSpecificFeature2());Require(plane!=null,"REFERENCE_PLANE_INVALID");
            var axes=Enumerable.Range(0,3).Select(i=>PlaneBasis(app,plane,i)).ToArray();
            for(int i=0;i<3;i++)Require(Math.Abs(Norm(axes[i])-1)<1e-7,"REFERENCE_BASIS_INVALID");
            for(int i=0;i<3;i++)for(int j=i+1;j<3;j++)Require(Math.Abs(Dot(axes[i],axes[j]))<1e-7,"REFERENCE_BASIS_NOT_ORTHOGONAL");
            foreach(var raw in rows){
                var row=raw as Dictionary<string,object>;Require(row!=null&&row.ContainsKey("face")&&row.ContainsKey("force_N"),"INVALID_LOAD_ROW");
                var force=Triple(row["force_N"],"force_N");Require(Norm(force)>0,"ZERO_FORCE");
                var face=Keep((IFace2)FaceById(model,Convert.ToString(row["face"])));
                var comps=axes.Select(axis=>Dot(force,axis)).ToArray();
                planned.Add(Tuple.Create(face,force,comps));
            }
            Require(planned.Count>0&&planned.Count<=16,"INVALID_LOAD_COUNT");
            var readbacks=new List<object>();
            foreach(var plan in planned){
                int mask=0;var values=new double[3];for(int i=0;i<3;i++){bool active=Math.Abs(plan.Item3[i])>1e-10;values[i]=active?plan.Item3[i]:1.0;if(active)mask|=1<<i;}
                Require(mask!=0,"FORCE_DIRECTION_UNRESOLVED");
                model.ClearSelection2(true);Require(feature.Select2(false,0),"REFERENCE_SELECTION_FAILED");
                var direction=Keep(Keep((ISelectionMgr)model.SelectionManager).GetSelectedObject6(1,-1));
                Require(direction!=null,"REFERENCE_SELECTION_EMPTY");model.ClearSelection2(true);
                int error=0;MutationStarted=true;
                var load=Keep((ICWForce)Call("AddForce3(global vector)",()=>lm.AddForce3(0,0,2,0,0,0,new double[0],new double[0],false,false,0,0,mask,0,values,false,false,new object[]{plan.Item1},direction,false,out error)));
                Require(error==0&&load!=null,"FORCE_FAILED: "+error);
                int x=0,y=0,z=0;double fx=0,fy=0,fz=0;
                load.GetForceComponentValues(out x,out y,out z,out fx,out fy,out fz);
                var actual=new[]{fx,fy,fz};for(int i=0;i<3;i++)if((mask&(1<<i))!=0)Require(Math.Abs(actual[i]-plan.Item3[i])<1e-7,"FORCE_READBACK_FAILED");
                Require(load.Unit==0,"FORCE_UNIT_NOT_NEWTON");
                readbacks.Add(D("global_force_N",plan.Item2,"reference_components_N",plan.Item3,"readback_components_N",actual,"active_mask",mask,"unit",load.Unit));
            }
            Require(lm.Count==1+planned.Count,"LOAD_COUNT_READBACK_FAILED");
            d["loads"]=readbacks;d["reference_basis_global"]=axes;d["boundaries"]=BoundaryState(lm);return d;
        }
        if(op=="phase3_rollers"){
            Require(lm.Count>=2,"EXPECTED_FIXED_AND_FORCES: inspect before axial retainers");
            for(int i=0;i<lm.Count;i++){int e=0;var b=Keep((ICWLoadsAndRestraints)lm.GetLoadsAndRestraints(i,out e));
                Require(e==0&&b!=null&&b.Type==(i==0?2:3),"EXISTING_ROLLER_OR_UNEXPECTED_BOUNDARY");}
            int oldCount=lm.Count;
            var raw=p.ContainsKey("faces")?p["faces"] as IEnumerable:null;Require(raw!=null,"ROLLER_FACES_REQUIRED");
            var faces=new List<IFace2>();foreach(var id in raw){
                var face=Keep((IFace2)FaceById(model,Convert.ToString(id)));
                var surface=Keep((ISurface)face.GetSurface());Require(surface.IsPlane(),"ROLLER_FACE_NOT_PLANAR");
                var plane=Numbers(surface.PlaneParams);Require(Math.Abs(Math.Abs(plane[1])-1)<1e-6,"ROLLER_FACE_NOT_AXIAL");
                faces.Add(face);
            }
            Require(faces.Count==2,"TWO_AXIAL_ROLLER_FACES_REQUIRED");
            var added=new List<object>();foreach(var face in faces){int error=0;MutationStarted=true;
                var roller=Keep((ICWRestraint)Call("AddRestraint(roller axial)",()=>lm.AddRestraint((int)swsRestraintType_e.swsRestraintTypeRoller,new object[]{face},null,out error)));
                Require(error==0&&roller!=null&&roller.RestraintType==(int)swsRestraintType_e.swsRestraintTypeRoller,"ROLLER_FAILED: "+error);
                added.Add(D("type","roller","axis","face_normal_Y"));
            }
            Require(lm.Count==oldCount+2,"ROLLER_COUNT_READBACK_FAILED");d["rollers"]=added;d["boundaries"]=BoundaryState(lm);return d;
        }
        if(op=="phase3_guide"){
            Require(lm.Count>=4,"EXPECTED_FIXED_FORCES_TWO_ROLLERS: inspect before guide");
            int oldCount=lm.Count;for(int i=0;i<oldCount;i++){int e=0;var b=Keep((ICWLoadsAndRestraints)lm.GetLoadsAndRestraints(i,out e));
                int expected=i==0||i>=oldCount-2?2:3;Require(e==0&&b!=null&&b.Type==expected,"UNEXPECTED_BOUNDARY_BEFORE_GUIDE");}
            var face=Keep((IFace2)FaceById(model,Arg(p,"face")));
            var surface=Keep((ISurface)face.GetSurface());Require(surface.IsPlane(),"GUIDE_FACE_NOT_PLANAR");
            var planeFace=Numbers(surface.PlaneParams);Require(Math.Abs(Math.Abs(planeFace[1])-1)<1e-6,"GUIDE_FACE_NOT_PIN_CAP");
            var feature=Keep((IFeature)((IPartDoc)model).FeatureByName("Right Plane"));
            if(feature==null)feature=Keep((IFeature)((IPartDoc)model).FeatureByName("右视基准面"));
            Require(feature!=null,"RIGHT_PLANE_NOT_FOUND");
            var refPlane=Keep((IRefPlane)feature.GetSpecificFeature2());Require(refPlane!=null,"GUIDE_PLANE_INVALID");
            var axes=Enumerable.Range(0,3).Select(i=>PlaneBasis(app,refPlane,i)).ToArray();
            Require(Math.Abs(Math.Abs(axes[0][2])-1)<1e-7,"GUIDE_DIR1_NOT_GLOBAL_Z");
            model.ClearSelection2(true);Require(feature.Select2(false,0),"GUIDE_REFERENCE_SELECTION_FAILED");
            var direction=Keep(Keep((ISelectionMgr)model.SelectionManager).GetSelectedObject6(1,-1));
            Require(direction!=null,"GUIDE_REFERENCE_SELECTION_EMPTY");model.ClearSelection2(true);
            int error=0;MutationStarted=true;
            var guide=Keep((ICWRestraint)Call("AddRestraint(reference plane guide)",()=>lm.AddRestraint((int)swsRestraintType_e.swsRestraintTypeReferenceGeometry,new object[]{face},direction,out error)));
            Require(error==0&&guide!=null,"GUIDE_CREATE_FAILED: "+error);
            guide.RestraintBeginEdit();guide.SetReferenceGeometry(direction);
            guide.SetTranslationComponentsValues(1,0,0,0,0,0);
            error=guide.RestraintEndEdit();Require(error==0,"GUIDE_END_EDIT_FAILED: "+error);
            int b1=0,b2=0,b3=0;double v1=0,v2=0,v3=0;
            guide.GetTranslationComponentsValues(out b1,out b2,out b3,out v1,out v2,out v3);
            Require(b1==1&&b2==0&&b3==0&&Math.Abs(v1)<1e-12&&lm.Count==oldCount+1,"GUIDE_READBACK_FAILED");
            d["guide_direction_global"]=axes[0];d["guide_components_enabled"]=new[]{b1,b2,b3};d["guide_values_m"]=new[]{v1,v2,v3};d["boundaries"]=BoundaryState(lm);return d;
        }
        if(op=="phase3_contacts"){
            var rawPairs=p.ContainsKey("pairs")?p["pairs"] as IEnumerable:null;Require(rawPairs!=null,"CONTACT_PAIRS_REQUIRED");
            var manager=Keep((ICWContactManager)study.ContactManager);Require(manager.ContactSetCount==0,"CONTACT_SET_ALREADY_EXISTS: inspect before retry");
            var planned=new List<Tuple<IFace2,IFace2,string,string,double>>();
            foreach(var raw in rawPairs){
                var row=raw as Dictionary<string,object>;Require(row!=null&&row.ContainsKey("link_face")&&row.ContainsKey("pin_face"),"INVALID_CONTACT_PAIR");
                var a=Keep((IFace2)FaceById(model,Convert.ToString(row["link_face"])));
                var b=Keep((IFace2)FaceById(model,Convert.ToString(row["pin_face"])));
                string an=Keep((IBody2)a.GetBody()).Name,bn=Keep((IBody2)b.GetBody()).Name;
                Require(!String.Equals(an,bn,StringComparison.OrdinalIgnoreCase),"CONTACT_SAME_BODY");
                var sa=Keep((ISurface)a.GetSurface());var sb=Keep((ISurface)b.GetSurface());
                Require(sa.IsCylinder()&&sb.IsCylinder(),"CYLINDRICAL_CONTACT_FACES_REQUIRED");
                var ca=Numbers(sa.CylinderParams);var cb=Numbers(sb.CylinderParams);
                Require(Math.Abs(ca[6]-cb[6])<2e-5,"CONTACT_RADII_MISMATCH");
                var ax=ca.Skip(3).Take(3).ToArray();var bx=cb.Skip(3).Take(3).ToArray();
                Require(Math.Abs(Math.Abs(Dot(ax,bx))-1)<1e-5,"CONTACT_AXES_NOT_PARALLEL");
                var delta=new[]{ca[0]-cb[0],ca[1]-cb[1],ca[2]-cb[2]};
                double along=Dot(delta,ax);var radial=new[]{delta[0]-along*ax[0],delta[1]-along*ax[1],delta[2]-along*ax[2]};
                Require(Norm(radial)<2e-5,"CONTACT_AXES_NOT_COAXIAL");
                planned.Add(Tuple.Create(a,b,an,bn,ca[6]*1000));
            }
            Require(planned.Count>0&&planned.Count<=8,"INVALID_CONTACT_PAIR_COUNT");
            // Free global contact prevents coplanar pin/end faces from bonding.
            // The explicit cylindrical pairs below supply the only contact path.
            MutationStarted=true;Call("SetGlobalContact(free)",()=>{manager.SetGlobalContact(1,0);return true;});
            int gt=0,go=0;manager.GetGlobalContact(out gt,out go);Require(gt==1,"GLOBAL_CONTACT_NOT_FREE");
            var made=new List<object>();
            foreach(var pair in planned){int error=0;MutationStarted=true;
                var contact=Keep((ICWContactSet)Call("CreateContactSet2(no penetration)",()=>manager.CreateContactSet2(0,0,new object[]{pair.Item1},new object[]{pair.Item2},out error)));
                Require(error==0&&contact!=null,"CONTACT_CREATE_FAILED: "+error);
                Require(contact.ContactSetType==0&&contact.SourceEntityCount==1&&contact.TargetEntityCount==1,"CONTACT_READBACK_FAILED");
                made.Add(D("name",contact.ContactName,"type","no_penetration","link_body",pair.Item3,"pin_body",pair.Item4,"radius_mm",pair.Item5));
            }
            Require(manager.ContactSetCount==planned.Count,"CONTACT_COUNT_READBACK_FAILED");d["contacts"]=made;return d;
        }
        if(op=="phase3_mesh"){
            var bodies=StudyBodies(study);Require(bodies.Count>=2,"MULTIBODY_REQUIRED");foreach(var body in bodies)MaterialData(body);
            Require(lm.Count>=2,"BOUNDARIES_REQUIRED");var contacts=Keep((ICWContactManager)study.ContactManager);
            Require(contacts.ContactSetCount>=1,"CONTACTS_REQUIRED");int gt=0,go=0;contacts.GetGlobalContact(out gt,out go);Require(gt==1,"GLOBAL_CONTACT_MUST_BE_FREE");
            double size=Convert.ToDouble(p["element_size_mm"]);Require(size>=1&&size<=20,"INVALID_MESH_SIZE");
            var mesh=Keep((ICWMesh)study.Mesh);mesh.Quality=(int)swsMeshQuality_e.swsMeshQualityHigh;mesh.MesherType=0;
            MutationStarted=true;int error=Call("CreateMesh(multibody,mm)",()=>study.CreateMesh((int)swsLinearUnit_e.swsLinearUnitMillimeters,size,size/20));
            Require(error==0,"MESH_FAILED: "+error);d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;d["element_size_mm"]=size;return d;
        }
        if(op=="phase3_run"){
            var bodies=StudyBodies(study);Require(bodies.Count>=2,"MULTIBODY_REQUIRED");foreach(var body in bodies)MaterialData(body);
            var mesh=Keep((ICWMesh)study.Mesh);Require(mesh.NodeCount>0&&mesh.ElementCount>0,"MESH_REQUIRED");
            var contacts=Keep((ICWContactManager)study.ContactManager);Require(contacts.ContactSetCount>=1,"CONTACTS_REQUIRED");
            string folder=Arg(p,"results_folder");Require(System.IO.Path.IsPathRooted(folder),"ABSOLUTE_RESULTS_FOLDER_REQUIRED");
            var options=Keep((ICWStaticStudyOptions)study.StaticStudyOptions);
            Require(String.Equals(System.IO.Path.GetFullPath(options.ResultFolder).TrimEnd('\\','/'),System.IO.Path.GetFullPath(folder).TrimEnd('\\','/'),StringComparison.OrdinalIgnoreCase),"RESULT_FOLDER_MISMATCH");
            options.LargeDisplacement=0;options.UseSoftSpring=Flag(p,"soft_spring")?1:0;options.UseInertialRelief=0;options.ComputeFreeBodyForce=1;
            MutationStarted=true;int error=Call("RunAnalysis(multibody contact)",()=>study.RunAnalysis());
            d["solver_error_code"]=error;d["solver_error_name"]=Enum.GetName(typeof(swsRunAnalysisError_e),error)??"UNKNOWN_SOLVER_ERROR";
            if(error!=0){d["status"]="error";d["error_code"]="SOLVER_FAILED";return d;}
            var results=Keep((ICWResults)study.Results);Require(results!=null,"SOLVER_NO_RESULTS");int re=0;
            var values=Numbers(Call("VerifyContactDisplacement",()=>results.GetMinMaxDisplacement(3,1,null,0,out re)));
            Require(re==0&&values.Length==4,"SOLVER_RESULTS_NOT_READABLE");
            d["max_displacement_mm"]=values[3];d["soft_spring"]=options.UseSoftSpring==1;d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;return d;
        }
        if(op=="phase3_results"){
            var results=Keep((ICWResults)study.Results);Require(results!=null,"RESULTS_UNAVAILABLE");int error=0;
            var disp=Numbers(results.GetMinMaxDisplacement(3,1,null,0,out error));Require(error==0&&disp.Length==4,"DISPLACEMENT_RESULTS_FAILED");
            d["min_displacement_mm"]=disp[1];d["max_displacement_mm"]=disp[3];d["max_node"]=disp[2];
            var mesh=Keep((ICWMesh)study.Mesh);double px=0,py=0,pz=0;
            int locationError=mesh.GetNodeLocation((int)disp[2],out px,out py,out pz);
            d["max_location_mm"]=new[]{px*1000,py*1000,pz*1000};d["max_location_error"]=locationError;
            var components=new List<object>();foreach(int component in new[]{0,1,2}){
                var v=Numbers(results.GetMinMaxDisplacement(component,1,null,0,out error));Require(error==0&&v.Length==4,"DISPLACEMENT_COMPONENT_FAILED");
                components.Add(D("component",component,"min_mm",v[1],"max_mm",v[3]));
            }d["component_extrema"]=components;
            var stress=Numbers(results.GetMinMaxStress(9,0,1,null,3,out error));Require(error==0&&stress.Length==4,"STRESS_RESULTS_FAILED");
            d["max_von_mises_MPa"]=stress[3];d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;
            if(p.ContainsKey("fixed_face")){
                var face=FaceById(model,Arg(p,"fixed_face"));object combined=null,selected=null;
                results.GetReactionForcesAndMomentsWithSelections(1,null,0,new object[]{face},out combined,out selected,out error);
                d["reaction_error"]=error;if(error==0)d["selected_reaction_N_Nm"]=Numbers(selected);
            }return d;
        }
        throw new InvalidOperationException("UNKNOWN_PHASE3_OPERATION");
    }
}
